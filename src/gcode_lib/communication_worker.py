import logging
import multiprocessing
import queue
import time

from gcode_lib.communication_interface import CommunicationInterface

log = logging.getLogger(__name__)

class CommunicationWorker(multiprocessing.Process):
    """
    Separate process that manages the active connection and acts as a watchdog.
    If the main process dies and heartbeats stop, it triggers a laser safety shutdown.
    """
    def __init__(self, driver: CommunicationInterface, safety_shutoff_command: str, timeout_sec: float = 0.5):
        super().__init__()
        self.driver = driver
        self.timeout_sec = timeout_sec
        self.safety_shutoff_command = safety_shutoff_command
        
        # IPC Queues for communicating with the main process
        self.cmd_queue = multiprocessing.Queue()
        self.response_queue = multiprocessing.Queue()
        
        # Flag to safely shut down the worker normally
        self._running = multiprocessing.Event()

    def run(self):
        """This runs in a completely separate OS process."""
        self._running.set()
        self.driver.connect()
        
        log.info("Communication worker started. Watchdog active.")

        while self._running.is_set():
            try:
                # Block and wait for a command or heartbeat from the main process.
                # If nothing arrives within timeout_sec, queue.Empty is raised.
                cmd = self.cmd_queue.get(timeout=self.timeout_sec)
                
                if cmd == "SHUTDOWN":
                    # Normal, graceful exit
                    self._running.clear()
                    break
                elif cmd == "HEARTBEAT":
                    # Do nothing, just keeps the timeout from expiring
                    continue
                else:
                    # Forward standard G-code/commands
                    self.driver.send(cmd)
                    
            except queue.Empty:
                # WATCHDOG TRIGGERED: Main process failed to send a heartbeat in time.
                log.error("Watchdog timeout! Main process unresponsive. Triggering E-STOP.")
                self.trigger_safety_shutdown()
                break

            # Handle incoming messages
            response = self.driver.read_message()
            if response:
                self.response_queue.put(response)

        self.driver.close()

    def trigger_safety_shutdown(self):
        """Immediately stop the machine and laser."""
        self.driver.send_message(self.safety_shutoff_command, respect_buffer=False)
        time.sleep(0.1) # Give the hardware buffer a fraction of a second to flush
        self.driver.terminate()
