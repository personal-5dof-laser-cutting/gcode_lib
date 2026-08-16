import logging
from queue import Empty
import threading
import os
import time
from typing import Optional

from gcode_lib.drivers.driver_interface import DriverInterface
from gcode_lib.communication_worker import CommunicationWorker

log = logging.getLogger(__name__)


class CommunicationProxy:
    """
    Main-process proxy that forwards commands over IPC to a CommunicationWorker process
    and maintains the watchdog heartbeat.
    """

    def __init__(self, driver: DriverInterface, heartbeat_interval: float = 0.2):
        self._driver = driver
        self._heartbeat_interval = heartbeat_interval
        self._worker = CommunicationWorker(driver=self._driver)
        self._is_closed = False

        self._owner_pid = os.getpid()

        # Heartbeat thread control
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()

        log.debug(
            "CommunicationProxy initialized with heartbeat_interval=%.3fs",
            heartbeat_interval,
        )

    def connect(
        self,
        setup_reporting: bool = True,
        timeout: float = 5.0,
        clear_messages: bool = True,
    ):
        """Start worker process, wait for ready event, and start heartbeat thread."""

        # TODO: This never terminates if hardware interface doesn't exist

        # WARN: This triggers when using context managers
        if not self._is_closed and self._worker and self._worker.is_alive():
            log.warning(
                "CommunicationProxy is already connected. Ignoring duplicate connect() call."
            )
            return self

        self._worker = CommunicationWorker(driver=self._driver)

        log.info("Starting CommunicationWorker process...")
        self._worker.start()

        log.debug("Waiting for worker process to signal driver ready...")
        if not self._worker.ready_event.wait(timeout=timeout):
            raise TimeoutError(
                "CommunicationWorker failed to connect to hardware within timeout."
            )

        self._is_closed = False

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
            log.debug(
                "Waiting for hardware boot banner and clearing startup messages..."
            )
            start_time = time.monotonic()
            boot_timeout = 2.0  # Max time to wait for boot splash

            while time.monotonic() - start_time < boot_timeout:
                # Wait up to 0.2s per check for MCU startup lines
                msg = self.read_message(timeout=0.2)
                if msg is None:
                    continue

                log.debug("Boot message skipped on connect: '%s'", msg)

                # Grbl / FluidNC welcome banner detected
                if "Grbl" in msg or "['$' for help]" in msg:
                    # Drain any trailing startup lines until 0.05s of silence
                    while (extra := self.read_message(timeout=0.05)) is not None:
                        log.debug("Boot message skipped on connect: '%s'", extra)
                    break

            log.debug("All initial boot messages cleared.")

        return self

    def _run_heartbeat(self):
        """Loop running in main process to keep the watchdog alive."""
        log.debug("Heartbeat thread loop active.")
        while not self._stop_heartbeat.wait(self._heartbeat_interval):
            self._worker.cmd_queue.put(("HEARTBEAT",))
        log.debug("Heartbeat thread loop terminated.")

    def close(self):
        """Gracefully close the heartbeat thread and shutdown worker process."""

        if self._is_closed or self._worker is None:
            return

        log.info("Closing CommunicationProxy gracefully...")

        log.debug("Sending SHUTDOWN command to worker process.")
        self._worker.cmd_queue.put(("SHUTDOWN",))

        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            log.debug("Waiting for heartbeat thread to join...")
            self._heartbeat_thread.join(timeout=1.0)

        log.debug("Waiting for worker process to join...")
        self._worker.join(timeout=2.0)
        self._is_closed = True
        log.info("CommunicationProxy closed.")

    def terminate(self):
        """Immediately kill the worker process."""
        log.warning("Terminating CommunicationProxy immediately!")
        self._stop_heartbeat.set()
        self._worker.terminate()
        log.info("CommunicationProxy terminated.")

    def queue_message(self, message: str):
        """Enqueue a message to be sent asynchronously."""
        log.debug("Queueing message to worker: %r", message)
        self._worker.cmd_queue.put(("QUEUE", message))

    def send_message(self, message: str, ensure_newline: bool = True):
        """Send a command directly to the worker process."""
        log.debug(
            "Sending message directly to worker (ensure_newline=%s): %r",
            ensure_newline,
            message,
        )
        self._worker.cmd_queue.put(("SEND_MESSAGE", message, ensure_newline))

    def send(self, message: str):
        """Infer message type and forward to worker process."""
        log.debug("Sending message with inferred routing to worker: %r", message)
        self._worker.cmd_queue.put(("SEND", message))

    def read_message(self, timeout: Optional[float] = None) -> Optional[str]:
        """Fetch an incoming message from the worker's response queue."""
        try:
            msg = self._worker.response_queue.get(block=(timeout != 0), timeout=timeout)
            log.debug("Read message from worker response queue: %r", msg)
            return msg
        except Empty:
            log.debug("Read message timeout, returning None")
            return None

    def setup_reporting(self):
        """Forward status/telemetry setup command to the worker process."""
        log.debug("Requesting SETUP_REPORTING from worker.")
        self._worker.cmd_queue.put(("SETUP_REPORTING",))

    def __del__(self):
        """Triggered when proxy is garbage collected"""
        # INFO: Ignore garbage collection if triggered inside child worker process
        if hasattr(self, "_owner_pid") and os.getpid() != self._owner_pid:
            return

        if hasattr(self, "_is_closed") and not self._is_closed:
            log.error(
                "CRITICAL: CommunicationProxy was garbage-collected without being closed!"
            )
            self.close()

    def __enter__(self):
        """Used for context managers"""
        # INFO: fallback if connect isn't explicitly called
        if self._is_closed:
            self.connect()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Used for contect managers"""
        self.close()
