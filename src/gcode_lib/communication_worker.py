import logging
import multiprocessing
import queue
import time

from gcode_lib.communication_interface import CommunicationInterface

log = logging.getLogger(__name__)


class CommunicationWorker(multiprocessing.Process):
    """
    Worker process that manages the active connection and acts as a watchdog.

    If the main process crashes or stops sending heartbeats, this worker
    triggers a safety shutdown to turn off the laser or spindle.
    """

    def __init__(
        self,
        driver: CommunicationInterface,
        timeout_sec: float = 0.5,
    ):
        """
        Initialize the communication worker.

        Parameters
        ----------
        driver : CommunicationInterface
            The underlying hardware driver. 
        timeout_sec : float, default 0.5
            Maximum seconds allowed between heartbeats before shutoff.
        """
        super().__init__()
        self.driver = driver
        self.timeout_sec = timeout_sec

        self.cmd_queue: multiprocessing.Queue = multiprocessing.Queue()
        self.response_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._running = multiprocessing.Event()

    def run(self):
        """Run the event loop in a separate process."""
        self._running.set()
        self.driver.connect()

        log.info("Communication worker started. Watchdog active.")

        while self._running.is_set():
            try:
                cmd = self.cmd_queue.get(timeout=self.timeout_sec)

                if cmd == "SHUTDOWN":
                    self._running.clear()
                    break
                elif cmd == "HEARTBEAT":
                    continue
                elif isinstance(cmd, tuple):
                    self._handle_tuple_command(cmd)
                elif isinstance(cmd, str):
                    self.driver.send(cmd)

            except queue.Empty:
                log.error("Watchdog timeout! Main process unresponsive. Triggering E-STOP.")
                self.trigger_safety_shutdown()
                break

            response = self.driver.read_message()
            if response:
                self.response_queue.put(response)

        self.driver.close()

    def _handle_tuple_command(self, cmd: tuple):
        """Unpack and execute commands sent from the proxy."""
        action = cmd[0]

        if action == "QUEUE":
            _, message = cmd
            self.driver.queue_message(message)
        elif action == "SEND_MESSAGE":
            _, message, respect_buffer = cmd
            self.driver.send_message(message, respect_buffer=respect_buffer)
        elif action == "SEND":
            _, message = cmd
            self.driver.send(message)
        else:
            log.warning("Unknown command action received: %s", action)

    def trigger_safety_shutdown(self):
        """Immediately stop the machine and terminate the driver connection."""
        self.driver.send_message(self.driver.safety_shutoff_command, respect_buffer=False)
        time.sleep(0.1)
        self.driver.terminate()
