import logging
from queue import Queue
from typing import Optional

from gcode_lib.communication_interface import CommunicationInterface

log = logging.getLogger(__name__)

class FluidNCSerialDriver(CommunicationInterface):
    """Serial communication driver for FluidNC."""

    _port: str
    _baudrate: int

    _send_queue: Queue
    _recv_queue: Queue

    _safety_shutoff_command: str

    def __init__(self, port: str, baudrate: int = 115200, safety_shutoff_command: str = "\x18"):
        """
        Initialize the serial driver.

        Parameters
        ----------
        port : str
            The serial port to use.
        baudrate : int, default 115200
            The baud rate for the connection.
        safety_shutoff_command : str, default "\x18"
            The command sent to the hardware on watchdog timeout.
        """
        assert baudrate > 0, "Baud rate must be positive."
        assert safety_shutoff_command, "Safety shutoff command must be set."

        self._port = port
        self._baudrate = baudrate

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
