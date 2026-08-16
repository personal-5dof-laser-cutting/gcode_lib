import logging
import multiprocessing
import queue
import time
from collections import deque

from gcode_lib.drivers.driver_interface import DriverInterface

log = logging.getLogger(__name__)

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

        # Dedicated process synchronization events
        self._running = multiprocessing.Event()
        self.ready_event = multiprocessing.Event()

        # Buffer tracking
        self._outbound_queue: deque[str] = deque()
        self._pending_line_lengths: deque[int] = deque()

    @property
    def bytes_in_buffer(self) -> int:
        return sum(self._pending_line_lengths)

    def run(self):
        self._running.set()
        log.info("Communication worker process started (PID: %s).", self.pid)

        try:
            log.info("Connecting to hardware driver...")
            self.driver.connect()
            log.info(
                "Driver connected successfully. Waiting for initial heartbeat to arm watchdog (timeout=%.2fs).",
                self.timeout_sec,
            )
            # Signal proxy that hardware connection is ready
            self.ready_event.set()
        except Exception:
            log.exception("Failed to establish connection with driver.")
            self._running.clear()
            return

        watchdog_armed = False
        last_heartbeat = time.monotonic()

        while self._running.is_set():
            # -------------------------------------------------------------
            # 1. Process IPC commands from Proxy
            # -------------------------------------------------------------
            try:
                cmd = self.cmd_queue.get(timeout=0.002)

                # Reset watchdog timer on any incoming IPC communication
                last_heartbeat = time.monotonic()
                watchdog_armed = True

                # Normalize tuple vs string messages
                if isinstance(cmd, str):
                    action, args = cmd, ()
                elif isinstance(cmd, tuple) and len(cmd) > 0:
                    action, args = cmd[0], cmd[1:]
                else:
                    log.warning("Received unsupported command type: %s", type(cmd))
                    continue

                # Unified command dispatch
                if action == "SHUTDOWN":
                    log.info(
                        "Shutdown command received. Exiting worker loop gracefully."
                    )
                    self._running.clear()
                    break

                elif action == "HEARTBEAT":
                    pass  # Heartbeat timestamp updated above

                elif action in ("QUEUE", "SEND"):
                    self._enqueue_gcode(args[0])

                elif action == "SEND_MESSAGE":
                    message, ensure_newline = args
                    if ensure_newline:
                        self._enqueue_gcode(message)
                    else:
                        log.debug("Sending real-time message immediately: %r", message)
                        self.driver.send_message(message, ensure_newline=False)

                elif action == "SETUP_REPORTING":
                    log.debug("Setting up status reporting...")
                    self.driver.setup_reporting()

                else:
                    log.warning("Unknown command action received: %s", action)

            except queue.Empty:
                pass

            # -------------------------------------------------------------
            # 2. Watchdog Check (Only active once armed)
            # -------------------------------------------------------------
            if watchdog_armed and (
                time.monotonic() - last_heartbeat > self.timeout_sec
            ):
                log.error(
                    "Watchdog timeout! No heartbeat received within %.2fs. "
                    "Main process may be unresponsive. Triggering E-STOP.",
                    self.timeout_sec,
                )
                self.trigger_safety_shutdown()
                break

            # -------------------------------------------------------------
            # 3. Read incoming hardware responses
            # -------------------------------------------------------------
            try:
                while True:
                    response = self.driver.read_message()
                    if not response:
                        break

                    log.debug("Received driver response: %s", response)

                    if self._is_ack_response(response):
                        if self._pending_line_lengths:
                            released_bytes = self._pending_line_lengths.popleft()
                            log.debug(
                                "ACK received. Freed %d bytes from line buffer. Remaining: %d",
                                released_bytes,
                                self.bytes_in_buffer,
                            )

                    self.response_queue.put(response)

            except Exception:
                log.exception("Error reading incoming message from driver.")

            # -------------------------------------------------------------
            # 4. Flush outbound G-code queue to driver
            # -------------------------------------------------------------
            self._flush_outbound_queue()

        # Shutdown cleanup
        log.info("Closing communication driver...")
        try:
            self.driver.close()
            log.info("Communication driver closed successfully.")
        except Exception:
            log.exception("Error while closing driver connection.")

    def _enqueue_gcode(self, message: str):
        clean_msg = message.strip()
        if clean_msg:
            self._outbound_queue.append(clean_msg)

    def _flush_outbound_queue(self):
        while self._outbound_queue:
            next_msg = self._outbound_queue[0]
            msg_len = len(next_msg) + 1

            if self.bytes_in_buffer + msg_len <= self.buffer_size:
                msg = self._outbound_queue.popleft()
                log.debug(
                    "Sending buffered G-code (len=%d, buffer_bytes=%d): %s",
                    msg_len,
                    self.bytes_in_buffer + msg_len,
                    msg,
                )
                self.driver.send_message(msg, ensure_newline=True)
                self._pending_line_lengths.append(msg_len)
            else:
                break

    @staticmethod
    def _is_ack_response(response: str) -> bool:
        resp = response.strip().lower()
        return resp == "ok" or resp.startswith("error:")

    def trigger_safety_shutdown(self):
        log.critical("E-STOP TRIGGERED! Initiating emergency hardware shutoff...")
        try:
            self.driver.send_message(
                self.driver.safety_shutoff_command, ensure_newline=False
            )
            log.info("Safety shutoff command sent.")
            self.driver.terminate()
            log.info("Driver connection terminated.")
        except Exception:
            log.exception("Failed to complete safety shutdown cleanly!")
