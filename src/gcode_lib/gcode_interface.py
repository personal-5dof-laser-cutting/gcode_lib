from abc import ABC, abstractmethod
import logging
from queue import Queue
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

    def send(self, message: str):
        pass

    def read_line(self):
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

    def send(self, message: str):
        pass

    def read_line(self, message: str):
        pass

class CommunicationWorker:
    """Worker class for handling communication tasks."""

    def __init__(self) -> None:
        pass

class Connection:
    """Class representing a single connection state."""

    def __init__(self) -> None:
        pass
