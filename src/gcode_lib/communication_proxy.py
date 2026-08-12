import logging
from queue import Empty
import threading
import time
from typing import Optional

from gcode_lib.communication_interface import CommunicationInterface
from gcode_lib.communication_worker import CommunicationWorker

log = logging.getLogger(__name__)


class CommunicationProxy(CommunicationInterface):
    """
    Main-process proxy that implements CommunicationInterface.

    Forwards commands over IPC to a CommunicationWorker process
    and maintains the watchdog heartbeat.
    """

    def __init__(self, driver: CommunicationInterface, heartbeat_interval: float = 0.2):
        self._driver = driver
        self._heartbeat_interval = heartbeat_interval

        # Initialize the background process
        self._worker = CommunicationWorker(driver=self._driver)

        # Heartbeat thread control
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()

    def connect(self):
        """Start the worker process and launch the main process heartbeat thread."""
        self._worker.start()

        # Start sending heartbeats from the main process
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._run_heartbeat, daemon=True
        )
        self._heartbeat_thread.start()

    def _run_heartbeat(self):
        """Loop running in the main process to keep the watchdog alive."""
        while not self._stop_heartbeat.is_set():
            self._worker.cmd_queue.put("HEARTBEAT")
            time.sleep(self._heartbeat_interval)

    def close(self):
        """Gracefully close the heartbeat thread and shutdown worker process."""
        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=1.0)

        self._worker.cmd_queue.put("SHUTDOWN")
        self._worker.join(timeout=2.0)

    def terminate(self):
        """Immediately kill the worker process."""
        self._stop_heartbeat.set()
        self._worker.terminate()

    def queue_message(self, message: str):
        """Enqueue a message to be sent asynchronously."""
        self._worker.cmd_queue.put(("QUEUE", message))

    def send_message(self, message: str, respect_buffer: bool = True):
        """Send a command directly to the worker process."""
        self._worker.cmd_queue.put(("SEND_MESSAGE", message, respect_buffer))

    def send(self, message: str):
        """Infer message type and forward to worker process."""
        self._worker.cmd_queue.put(("SEND", message))

    def read_message(self) -> Optional[str]:
        """Fetch an incoming message from the worker's response queue without blocking."""
        try:
            return self._worker.response_queue.get_nowait()
        except Empty:
            return None

    def get_state(self) -> Optional[str]:
        """Request state updating or query the underlying driver state."""
        self._worker.cmd_queue.put(("GET_STATE",))

    def setup_reporting(self):
        """Forward status/telemetry setup command to the worker process."""
        self._worker.cmd_queue.put(("SETUP_REPORTING",))

    @property
    def safety_shutoff_command(self) -> str:
        """Retrieve the static safety shutoff command sequence directly from the driver."""
        return self._driver.safety_shutoff_command
