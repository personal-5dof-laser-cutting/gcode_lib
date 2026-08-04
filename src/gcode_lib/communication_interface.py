from abc import ABC, abstractmethod
from queue import Queue
from typing import Optional


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






