import logging
import multiprocessing
import queue
import time
from collections import deque

from gcode_lib.drivers.driver_interface import DriverInterface

log = logging.getLogger(__name__)

# TODO: this should live in the driver
GRBL_RX_BUFFER_SIZE = 128


class CommunicationWorker(multiprocessing.Process):
    """
    Worker process that manages the active connection, line buffer, and watchdog.
    """

    def __init__(
        self,
        driver: DriverInterface,
        timeout_sec: float = 0.5,
        buffer_size: int = GRBL_RX_BUFFER_SIZE,
    ):
        super().__init__()
        self.driver = driver
        self.timeout_sec = timeout_sec
        self.buffer_size = buffer_size

        self.cmd_queue: multiprocessing.Queue = multiprocessing.Queue()
        self.response_queue: multiprocessing.Queue = multiprocessing.Queue()

        self._running = multiprocessing.Event()
        self.ready_event = multiprocessing.Event()

        self._outbound_queue: deque[str] = deque()
        self._pending_line_lengths: deque[int] = deque()

    @property
    def bytes_in_buffer(self) -> int:
        return sum(self._pending_line_lengths)

    def run(self):
        self._running.set()
        log.info("Communication worker process started (PID: %s).", self.pid)

        try:
            self.driver.connect()
            self.ready_event.set()
        except Exception:
            log.exception("Failed to establish connection with driver.")
            self._running.clear()
            return

        watchdog_armed = False
        last_heartbeat = time.monotonic()

        while self._running.is_set():
            # 1. Process IPC commands from Proxy
            try:
                cmd = self.cmd_queue.get(timeout=0.002)

                # Any command from the proxy counts as a heartbeat
                last_heartbeat = time.monotonic()
                watchdog_armed = True

                if isinstance(cmd, str):
                    action, args = cmd, ()
                elif isinstance(cmd, tuple) and len(cmd) > 0:
                    action, args = cmd[0], cmd[1:]
                else:
                    continue

                if action == "SHUTDOWN":
                    self._running.clear()
                    break
                elif action == "HEARTBEAT":
                    pass
                elif action in ("QUEUE", "SEND"):
                    self._enqueue_gcode(args[0])
                elif action == "SEND_REALTIME":
                    # Bypasses the queue and buffer entirely
                    self.driver.send_message(args[0], append_newline=False)
                elif action == "SETUP_REPORTING":
                    self.driver.setup_reporting()

            except queue.Empty:
                pass

            # 2. Watchdog Check
            if watchdog_armed and (
                time.monotonic() - last_heartbeat > self.timeout_sec
            ):
                log.error("Watchdog timeout! Triggering E-STOP.")
                self.trigger_safety_shutdown()
                self._send_system_event("WATCHDOG_TIMEOUT")
                break

            # 3. Read incoming hardware responses
            try:
                while True:
                    response = self.driver.read_message()
                    if not response:
                        break

                    if self._is_ack_response(response) and self._pending_line_lengths:
                        self._pending_line_lengths.popleft()

                    # Push to proxy, but don't block forever if proxy is dead
                    try:
                        self.response_queue.put(response, timeout=0.01)
                    except queue.Full:
                        log.error("Response queue full! Proxy process is unresponsive.")
                        self.trigger_safety_shutdown()
                        self._running.clear()
                        break

            except Exception:
                log.exception("Unexpected error reading incoming message.")

            # 4. Flush outbound G-code queue to driver
            self._flush_outbound_queue()

        # Shutdown cleanup
        try:
            self.driver.close()
        except Exception:
            log.exception("Error while closing driver connection.")

    def _enqueue_gcode(self, message: str):
        clean_msg = message.strip()
        if clean_msg:
            self._outbound_queue.append(clean_msg)

    def _flush_outbound_queue(self):
        while self._outbound_queue:
            next_msg = self._outbound_queue[0]
            msg_len = len(next_msg) + 1  # +1 for newline character

            if self.bytes_in_buffer + msg_len <= self.buffer_size:
                msg = self._outbound_queue.popleft()
                self.driver.send(msg)  # Uses our new smart send()
                self._pending_line_lengths.append(msg_len)
            else:
                break

    def _send_system_event(self, event_name: str):
        """Send internal state events back to the Proxy process."""
        try:
            self.response_queue.put(f"SYS:{event_name}", timeout=0.01)
        except queue.Full:
            pass

    @staticmethod
    def _is_ack_response(response: str) -> bool:
        # TODO: Move to driver interface: return self.driver.is_ack(response)
        resp = response.strip().lower()
        return resp == "ok" or resp.startswith("error:")

    def trigger_safety_shutdown(self):
        try:
            self.driver.send_message(
                self.driver.safety_shutoff_command, append_newline=False
            )
            self.driver.terminate()
        except Exception:
            log.exception("Failed to complete safety shutdown cleanly!")
