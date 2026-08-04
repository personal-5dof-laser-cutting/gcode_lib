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
    
    _safety_shutoff_command: str

    def __init__(self, address: str, port: int, safety_shutoff_command: str = "\x18"):
        """
        Initialize the WebSockets driver.

        Parameters
        ----------
        address : str
            The network address to connect to.
        port : int
            The network port to use.
        safety_shutoff_command : str, default "\x18"
            The command sent to the hardware on watchdog timeout.
        """
        assert safety_shutoff_command, "Safety shutoff command must be set."

        self._address = address
        self._port = port

        self._safety_shutoff_command = safety_shutoff_command


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

    @property
    def safety_shutoff_command(self) -> str:
        return self._safety_shutoff_command
