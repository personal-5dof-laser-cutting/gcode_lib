import logging

from queue import Empty
import threading
import os
import time
from typing import Optional

from gcode_lib.drivers.driver_interface import DriverInterface
from gcode_lib.communication_worker import CommunicationWorker
import gcode_lib.ipc_commands as ipc

log = logging.getLogger(__name__)


class CommunicationProxy:
    """
    Control communication between the main process and hardware worker process.

    This proxy forwards commands over IPC to a dedicated worker process.
    It manages the watchdog heartbeat thread to maintain hardware connection.

    Parameters
    ----------
    driver : DriverInterface
        The hardware driver implementation instance.
    heartbeat_interval : float, default=0.2
        The time interval in seconds between heartbeat signals.

    Attributes
    ----------
    _driver : DriverInterface
        The stored hardware driver interface.
    _heartbeat_interval : float
        The configured time interval for heartbeats.
    _worker : Optional[CommunicationWorker]
        The active communication worker process instance.
    _is_connected : bool
        The current connection state flag.
    """

    def __init__(self, driver: DriverInterface, heartbeat_interval: float = 0.2):
        self._driver = driver
        self._heartbeat_interval = heartbeat_interval
        self._worker: Optional[CommunicationWorker] = None
        self._is_connected = False

        self._owner_pid = os.getpid()

        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()

        log.debug(
            "CommunicationProxy initialized with heartbeat_interval=%.3fs",
            heartbeat_interval,
        )

    @property
    def is_connected(self) -> bool:
        """
        Return the hardware connection status.

        Returns
        -------
        bool
            True if the worker process is running and connected; False otherwise.
        """
        return (
            self._is_connected and self._worker is not None and self._worker.is_alive()
        )

    def connect(
        self,
        setup_reporting: bool = True,
        timeout: float = 5.0,
        clear_messages: bool = True,
    ) -> "CommunicationProxy":
        """
        Start the worker process, verify connection, and start heartbeats.

        Parameters
        ----------
        setup_reporting : bool, default=True
            Set to True to send initial status reporting commands.
        timeout : float, default=5.0
            Maximum wait time in seconds for worker startup.
        clear_messages : bool, default=True
            Set to True to purge startup boot messages from hardware.

        Returns
        -------
        CommunicationProxy
            The connected proxy instance.

        Raises
        ------
        RuntimeError
            If the worker process is already running.
        TimeoutError
            If the worker process fails to signal readiness before timeout.
        """
        if self.is_connected:
            log.warning(
                "CommunicationProxy is already connected. Ignoring duplicate call."
            )
            return self

        self._worker = CommunicationWorker(driver=self._driver)

        log.info("Starting CommunicationWorker process...")
        self._worker.start()

        log.debug("Waiting for worker process to signal driver ready...")
        if not self._worker.ready_event.wait(timeout=timeout):
            self.terminate()
            raise TimeoutError(
                "CommunicationWorker failed to connect to hardware within timeout."
            )

        self._is_connected = True

        log.debug("Starting main process heartbeat thread.")
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._run_heartbeat, daemon=True
        )
        self._heartbeat_thread.start()

        if setup_reporting:
            log.debug("Triggering initial reporting setup.")
            self.setup_reporting()

        if clear_messages:
            self._clear_boot_messages()

        return self

    def _clear_boot_messages(self, boot_timeout: float = 2.0) -> None:
        """
        Read and discard hardware startup banner messages.

        Parameters
        ----------
        boot_timeout : float, default=2.0
            Maximum time in seconds to collect startup lines.
        """
        log.debug("Waiting for hardware boot banner and clearing startup messages...")
        start_time = time.monotonic()

        while time.monotonic() - start_time < boot_timeout:
            msg = self.read_message(timeout=0.2)
            if msg is None:
                continue

            log.debug("Boot message skipped on connect: '%s'", msg)

            if "Grbl" in msg or "['$' for help]" in msg:
                while (extra := self.read_message(timeout=0.05)) is not None:
                    log.debug("Boot message skipped on connect: '%s'", extra)
                break

        log.debug("All initial boot messages cleared.")

    def _run_heartbeat(self) -> None:
        """
        Send periodic heartbeat commands to the worker process queue.
        """
        log.debug("Heartbeat thread loop active.")
        while not self._stop_heartbeat.wait(self._heartbeat_interval):
            if self._worker and self._worker.is_alive():
                self._worker.cmd_queue.put(ipc.Heartbeat())
            else:
                log.error("Worker process died. Stopping heartbeat thread.")
                break
        log.debug("Heartbeat thread loop terminated.")

    def close(self) -> None:
        """
        Stop heartbeat signals and close the worker process gracefully.
        """
        if not self._is_connected or self._worker is None:
            return

        log.info("Closing CommunicationProxy gracefully...")

        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            log.debug("Waiting for heartbeat thread to join...")
            self._heartbeat_thread.join(timeout=1.0)

        log.debug("Sending shtudown command to worker process.")
        try:
            self._worker.cmd_queue.put(ipc.Shutdown())
            self._worker.join(timeout=2.0)
        except Exception as err:
            log.warning("Error during worker join: %s", err)

        if self._worker.is_alive():
            log.warning(
                "Worker did not shut down in time. Terminating worker forceably."
            )
            self._worker.terminate()
            self._worker.join(timeout=1.0)

        self._is_connected = False
        log.info("CommunicationProxy closed.")

    def terminate(self) -> None:
        """
        Terminate the worker process immediately without graceful shutdown.
        """
        log.warning("Terminating CommunicationProxy immediately!")
        self._stop_heartbeat.set()

        if self._worker is not None:
            if self._worker.is_alive():
                self._worker.terminate()
            self._worker.join(timeout=1.0)

        self._is_connected = False
        log.info("CommunicationProxy terminated.")

    def queue_message(self, message: str) -> None:
        """
        Put a message into the asynchronous worker queue.

        Parameters
        ----------
        message : str
            The G-code or driver command string to send.

        Raises
        ------
        RuntimeError
            If the proxy is not connected to the worker process.
        """
        self._verify_connection()
        log.debug("Queueing message to worker: %r", message)
        self._worker.cmd_queue.put(ipc.QueueMessage(message))

    def send_message(self, message: str, ensure_newline: bool = True) -> None:
        """
        Send a direct command payload to the worker process.

        Parameters
        ----------
        message : str
            The command payload string to send.
        ensure_newline : bool, default=True
            Set to True to append a trailing newline character.

        Raises
        ------
        RuntimeError
            If the proxy is not connected to the worker process.
        """
        self._verify_connection()
        log.debug("Sending direct message to worker: %r", message)
        self._worker.cmd_queue.put(ipc.SendMessage(message, ensure_newline))

    def send(self, message: str) -> None:
        """
        Send a raw command string to the worker process using auto-routing.

        Parameters
        ----------
        message : str
            The command string to route and process.

        Raises
        ------
        RuntimeError
            If the proxy is not connected to the worker process.
        """
        self._verify_connection()
        log.debug("Sending inferred message to worker: %r", message)
        self._worker.cmd_queue.put(ipc.Send(message))

    def read_message(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Fetch the next incoming message from the worker response queue.

        Parameters
        ----------
        timeout : Optional[float], default=None
            Maximum time in seconds to wait for a message. Pass 0 for non-blocking read.

        Returns
        -------
        Optional[str]
            The received message text string, or None if the queue is empty.

        Raises
        ------
        RuntimeError
            If the proxy is not connected to the worker process.
        """
        self._verify_connection()
        block_flag = timeout is None or timeout > 0
        try:
            msg = self._worker.response_queue.get(block=block_flag, timeout=timeout)
            log.debug("Read message from response queue: %r", msg)
            return msg
        except Empty:
            return None

    def setup_reporting(self, interval_ms: int = 0) -> None:
        """
        Send the telemetry setup instruction to the worker process.

        Raises
        ------
        RuntimeError
            If the proxy is not connected to the worker process.
        """
        self._verify_connection()
        log.debug("Requesting SETUP_REPORTING from worker.")
        self._worker.cmd_queue.put(ipc.SetupReporting(interval_ms))

    def _verify_connection(self) -> None:
        """
        Verify that the worker process is running and active.

        Raises
        ------
        RuntimeError
            If the communication worker process is dead or disconnected.
        """
        if not self.is_connected:
            raise RuntimeError(
                "CommunicationProxy is not connected to an active worker."
            )

    def __del__(self) -> None:
        """
        Close resources when the garbage collector removes the instance.
        """
        if hasattr(self, "_owner_pid") and os.getpid() != self._owner_pid:
            return

        if hasattr(self, "_is_connected") and self._is_connected:
            log.error(
                "CRITICAL: CommunicationProxy garbage-collected without explicit close!"
            )
            self.close()

    def __enter__(self) -> "CommunicationProxy":
        """
        Connect to hardware when entering the context manager block.

        Returns
        -------
        CommunicationProxy
            The connected proxy instance.
        """
        if not self.is_connected:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Close connections when exiting the context manager block.
        """
        self.close()
