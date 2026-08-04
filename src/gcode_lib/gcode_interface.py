from abc import ABC, abstractmethod
import logging
import multiprocessing
import queue
from queue import Queue
import time
from typing import Optional

log = logging.getLogger(__name__)

class CommunicationInterface(ABC):
    """Base class for communication interfaces."""

    _send_queue: Queue
    _recv_queue: Queue

    @abstractmethod
    def connect(self):
        """Establish a connection using the detected channel."""
        pass
            
    @abstractmethod
    def close(self):
        """Close the connection gracefully and wait for confirmation."""
        pass
    
    @abstractmethod
    def terminate(self):
        """Send the termination signal and exit."""
        pass
    
    @abstractmethod
    def queue_message(self, message: str):
        """
        Add a message to the send queue.

        Parameters
        ----------
        message : str
            The message to add.
        """
        pass

    @abstractmethod
    def send_message(self, message: str, respect_buffer: bool = True):
        """
        Skip the send queue and send the message directly.

        Parameters
        ----------
        message : str
            The message to send.
        respect_buffer : bool, default True
            If True, wait for space in the remote buffer before sending.
        """
        pass
    
    @abstractmethod
    def send(self, message: str):
        """
        Infer the send method based on the message type.

        Parameters
        ----------
        message : str
            The message to send.
        """
        pass
    
    @abstractmethod
    def read_message(self) -> Optional[str]:
        """
        Read a message from the receive buffer.

        Returns
        -------
        str or None
            The message if the buffer is not empty, otherwise None.
        """
        pass

class CommunicationWorker(multiprocessing.Process):
    """
    Separate process that manages the active connection and acts as a watchdog.
    If the main process dies and heartbeats stop, it triggers a laser safety shutdown.
    """
    def __init__(self, driver: 'CommunicationInterface', timeout_sec: float = 0.5):
        super().__init__()
        self.driver = driver
        self.timeout_sec = timeout_sec
        
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
                    # Forward standard G-code/commands to FluidNC
                    self.driver.send(cmd)
                    
            except queue.Empty:
                # WATCHDOG TRIGGERED: Main process failed to send a heartbeat in time.
                log.error("Watchdog timeout! Main process unresponsive. Triggering E-STOP.")
                self.trigger_safety_shutdown()
                break

            # Handle incoming messages from FluidNC (optional, non-blocking)
            response = self.driver.read_message()
            if response:
                self.response_queue.put(response)

        self.driver.close()

    def trigger_safety_shutdown(self):
        """Immediately stop the machine and laser."""
        # \x18 is the Grbl/FluidNC Realtime Command for Soft-Reset.
        # It instantly halts motion, turns off the laser/spindle, and enters ALARM state.
        self.driver.send_message("\x18", respect_buffer=False)
        time.sleep(0.1) # Give the hardware buffer a fraction of a second to flush
        self.driver.terminate()

class FluidNCSerialDriver(CommunicationInterface):
    """Serial communication driver for FluidNC."""

    _port: str
    _baudrate: int

    _send_queue: Queue
    _recv_queue: Queue

    def __init__(self, port: str, baudrate: int = 115200):
        """
        Initialize the serial driver.

        Parameters
        ----------
        port : str
            The serial port to use.
        baudrate : int, default 115200
            The baud rate for the connection.
        """
        assert baudrate > 0, "Baud rate must be positive."

        self._port = port
        self._baudrate = baudrate

    def connect(self):
        pass

    def close(self):
        pass

    def terminate(self):
        pass

    def queue_message(self, message: str):
        pass

    def send_message(self, message: str, respect_buffer: bool = True):
        pass

    def send(self, message: str):
        pass

    def read_message(self) -> Optional[str]:
        pass

class FluidNCWebsocketsDriver(CommunicationInterface):
    """WebSockets communication driver for FluidNC."""

    _address: str
    _port: int

    _send_queue: Queue
    _recv_queue: Queue

    def __init__(self, address: str, port: int):
        """
        Initialize the WebSockets driver.

        Parameters
        ----------
        address : str
            The network address to connect to.
        port : int
            The network port to use.
        """
        self._address = address
        self._port = port

    def connect(self):
        pass

    def close(self):
        pass

    def terminate(self):
        pass

    def queue_message(self, message: str):
        pass

    def send_message(self, message: str, respect_buffer: bool = True):
        pass

    def send(self, message: str):
        pass

    def read_message(self) -> Optional[str]:
        pass
