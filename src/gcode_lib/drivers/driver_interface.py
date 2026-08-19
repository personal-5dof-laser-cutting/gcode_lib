from abc import ABC, abstractmethod
from typing import Optional


class DriverInterface(ABC):
    """
    Define abstract communication methods for hardware drivers.

    All concrete driver implementations must inherit from this class
    and implement all abstract methods and properties.
    """

    @abstractmethod
    def connect(self) -> None:
        """
        Establish a physical hardware connection over the selected channel.

        Raises
        ------
        ConnectionError
            If the hardware connection fails to establish.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the hardware connection gracefully.
        """
        pass

    @abstractmethod
    def terminate(self) -> None:
        """
        Stop hardware communication immediately without graceful handshakes.
        """
        pass

    @abstractmethod
    def send_message(self, message: str, append_newline: bool = True) -> None:
        """
        Send a direct raw text string to the hardware interface.

        Parameters
        ----------
        message : str
            The raw text string to transmit.
        append_newline : bool, default=True
            Set to True to append a line break character to the message string.

        Raises
        ------
        IOError
            If transmission over the physical channel fails.
        """
        pass

    @abstractmethod
    def send(self, message: str) -> None:
        """
        Route and transmit a formatted command line to the hardware.

        Parameters
        ----------
        message : str
            The G-code or protocol command string to transmit.

        Raises
        ------
        IOError
            If transmission over the physical channel fails.
        """
        pass

    @abstractmethod
    def read_message(self) -> Optional[str]:
        """
        Read the next available text message line from the receive buffer.

        Returns
        -------
        Optional[str]
            The string line received from hardware, or None if no data exists.

        Raises
        ------
        IOError
            If reading from the physical channel fails.
        """
        pass

    @abstractmethod
    def setup_reporting(self, interval_ms: int) -> None:
        """
        Send initial configuration commands to enable hardware telemetry reporting.
        """
        pass

    @abstractmethod
    def is_ack(self, response: str) -> bool:
        """
        Check if a hardware response line is a command acknowledgment.

        Parameters
        ----------
        response : str
            The raw string line received from hardware.

        Returns
        -------
        bool
            True if the line is a recognized command acknowledgment; False otherwise.
        """
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        bool : True if the physical hardware connection is active; False otherwise.
        """
        pass

    @property
    @abstractmethod
    def rx_buffer_size(self) -> int:
        """
        int : The total capacity of the hardware serial receive buffer in bytes.
        """
        pass

    @property
    @abstractmethod
    def safety_shutoff_command(self) -> str:
        """
        str : The exact byte or string sequence required for emergency stop.
        """
        pass
