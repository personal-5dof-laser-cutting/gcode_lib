import logging
from queue import Queue
from typing import Optional

from gcode_lib.communication_interface import CommunicationInterface

log = logging.getLogger(__name__)

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
