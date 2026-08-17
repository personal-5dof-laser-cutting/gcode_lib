import logging
import multiprocessing
import queue
import time
from collections import deque

from gcode_lib.drivers.driver_interface import DriverInterface

log = logging.getLogger(__name__)


class CommunicationWorker(multiprocessing.Process):
    """
    Manage the active driver connection, command buffer, and hardware watchdog.

    This process receives IPC commands from the proxy, tracks hardware buffer limits,
    and sends safety shutoff signals if communication fails.

    Parameters
    ----------
    driver : DriverInterface
        The hardware driver implementation instance.
    timeout_sec : float, default=0.5
        The watchdog timeout period in seconds.
    buffer_size : int, default=128
        The maximum hardware receive buffer size in bytes.

    Attributes
    ----------
    driver : DriverInterface
        The assigned hardware driver instance.
    timeout_sec : float
        The stored watchdog timeout limit.
    buffer_size : int
        The stored maximum buffer capacity in bytes.
    cmd_queue : multiprocessing.Queue
        The input command queue from the proxy process.
    response_queue : multiprocessing.Queue
        The output response queue to the proxy process.
    ready_event : multiprocessing.Event
        The signal event set when hardware connection completes.
    """

    def __init__(
        self,
        driver: DriverInterface,
        timeout_sec: float = 0.5,
        buffer_size: int = 128,
    ):
        super().__init__()
        self.driver = driver
        self.timeout_sec = timeout_sec
        self.buffer_size = getattr(driver, "rx_buffer_size", buffer_size)

        self.cmd_queue: multiprocessing.Queue = multiprocessing.Queue()
        self.response_queue: multiprocessing.Queue = multiprocessing.Queue()

        self._running = multiprocessing.Event()
        self.ready_event = multiprocessing.Event()

        self._outbound_queue: deque[str] = deque()
        self._pending_line_lengths: deque[int] = deque()

    @property
    def bytes_in_buffer(self) -> int:
        """
        Calculate the current byte count in the hardware buffer.

        Returns
        -------
        int
            The total number of unacknowledged bytes in the hardware buffer.
        """
        return sum(self._pending_line_lengths)

    def run(self) -> None:
        """
        Execute the main worker loop to process commands and monitor hardware.
        """
        self._running.set()
        log.info("Communication worker process started (PID: %s).", self.pid)

        try:
            # 1. Hardware Connection Setup
            try:
                self.driver.connect()
                self.ready_event.set()
            except Exception:
                log.exception("Failed to establish connection with driver.")
                self._send_system_event("HARDWARE_DISCONNECTED")
                return

            watchdog_armed = False
            last_heartbeat = time.monotonic()

            # 2. Main Event Loop
            while self._running.is_set():
                work_done = False

                # Process IPC commands from Proxy
                try:
                    cmd = self.cmd_queue.get(timeout=0.002)
                    last_heartbeat = time.monotonic()
                    watchdog_armed = True
                    work_done = True
                    self._process_ipc_command(cmd)
                except queue.Empty:
                    pass

                # Check Watchdog Status
                if watchdog_armed and (
                    time.monotonic() - last_heartbeat > self.timeout_sec
                ):
                    log.error("Watchdog timeout! Triggering E-STOP.")
                    self.trigger_safety_shutdown()
                    self._send_system_event("WATCHDOG_TIMEOUT")
                    break

                # Read incoming hardware responses
                if self._read_hardware_responses():
                    work_done = True

                # Flush outbound G-code queue to driver
                if self._flush_outbound_queue():
                    work_done = True

                # Prevent high CPU spinning when idle
                if not work_done:
                    time.sleep(0.001)

        except Exception:
            log.exception("Unhandled exception in worker process execution loop!")
            self.trigger_safety_shutdown()
            self._send_system_event("HARDWARE_DISCONNECTED")
        finally:
            self._cleanup_driver()

    def _process_ipc_command(self, cmd: object) -> None:
        """
        Parse and execute a single IPC command received from the proxy.

        Parameters
        ----------
        cmd : object
            The raw command tuple or string from the command queue.
        """
        if isinstance(cmd, str):
            action, args = cmd, ()
        elif isinstance(cmd, tuple) and len(cmd) > 0:
            action, args = cmd[0], cmd[1:]
        else:
            return

        if action == "SHUTDOWN":
            self._running.clear()
        elif action == "HEARTBEAT":
            pass
        elif action in ("QUEUE", "SEND"):
            self._enqueue_gcode(args[0])
        elif action == "SEND_REALTIME":
            self.driver.send_message(args[0], ensure_newline=False)
        elif action == "SETUP_REPORTING":
            self.driver.setup_reporting()

    def _read_hardware_responses(self) -> bool:
        """
        Read pending response messages from the hardware driver.

        Returns
        -------
        bool
            True if one or more response lines were read; False otherwise.
        """
        received_any = False
        try:
            while True:
                response = self.driver.read_message()
                if not response:
                    break

                received_any = True

                if self._is_ack_response(response) and self._pending_line_lengths:
                    self._pending_line_lengths.popleft()

                try:
                    self.response_queue.put(response, timeout=0.01)
                except queue.Full:
                    log.error("Response queue full! Proxy process is unresponsive.")
                    self.trigger_safety_shutdown()
                    self._send_system_event("HARDWARE_DISCONNECTED")
                    self._running.clear()
                    break

        except Exception:
            log.exception("Unexpected error reading incoming message from driver.")
            self.trigger_safety_shutdown()
            self._send_system_event("HARDWARE_DISCONNECTED")
            self._running.clear()

        return received_any

    def _flush_outbound_queue(self) -> bool:
        """
        Send queued commands to the driver when hardware buffer space is available.

        Returns
        -------
        bool
            True if one or more messages were sent; False otherwise.
        """
        sent_any = False
        while self._outbound_queue:
            next_msg = self._outbound_queue[0]
            msg_len = len(next_msg) + 1

            if self.bytes_in_buffer + msg_len <= self.buffer_size:
                msg = self._outbound_queue.popleft()
                try:
                    self.driver.send(msg)
                    self._pending_line_lengths.append(msg_len)
                    sent_any = True
                except Exception:
                    log.exception("Failed to transmit command string to driver.")
                    self.trigger_safety_shutdown()
                    self._send_system_event("HARDWARE_DISCONNECTED")
                    self._running.clear()
                    break
            else:
                break

        return sent_any

    def _enqueue_gcode(self, message: str) -> None:
        """
        Format and append a G-code command string to the outbound queue.

        Parameters
        ----------
        message : str
            The raw command line string to add.
        """
        clean_msg = message.strip()
        if clean_msg:
            self._outbound_queue.append(clean_msg)

    def _flush_outbound_queue(self) -> bool:
        """
        Send queued commands to the driver when hardware buffer space is available.

        Returns
        -------
        bool
            True if one or more messages were sent; False otherwise.
        """
        sent_any = False
        while self._outbound_queue:
            next_msg = self._outbound_queue[0]
            msg_len = len(next_msg) + 1

            if self.bytes_in_buffer + msg_len <= self.buffer_size:
                msg = self._outbound_queue.popleft()
                try:
                    self.driver.send(msg)
                    self._pending_line_lengths.append(msg_len)
                    sent_any = True
                except Exception:
                    log.exception("Failed to transmit command string to driver.")
                    self.trigger_safety_shutdown()
                    self._running.clear()
                    break
            else:
                break

        return sent_any

    def _send_system_event(self, event_name: str) -> None:
        """
        Send an internal system notification message to the proxy response queue.

        Parameters
        ----------
        event_name : str
            The system event name identifier string.
        """
        try:
            self.response_queue.put(f"SYS:{event_name}", timeout=0.01)
        except queue.Full:
            pass

    def _is_ack_response(self, response: str) -> bool:
        """
        Check if a hardware response string is an acknowledgment signal.

        Parameters
        ----------
        response : str
            The raw response string received from the driver.

        Returns
        -------
        bool
            True if the line is a recognized command acknowledgment; False otherwise.
        """
        if hasattr(self.driver, "is_ack"):
            return self.driver.is_ack(response)

        resp = response.strip().lower()
        return resp == "ok" or resp.startswith("error:")

    def trigger_safety_shutdown(self) -> None:
        """
        Send emergency shutoff commands to stop the hardware safely.
        """
        try:
            safety_cmd = getattr(self.driver, "safety_shutoff_command", "\x18")
            self.driver.send_message(safety_cmd, ensure_newline=False)
            self.driver.terminate()
        except Exception:
            log.exception("Failed to complete safety shutdown cleanly!")

    def _cleanup_driver(self) -> None:
        """
        Close the active driver connection and release system resources.
        """
        try:
            self.driver.close()
        except Exception:
            log.exception("Error while closing driver connection.")
