import logging
import time
from typing import Optional

import serial
from serial import SerialException, SerialTimeoutException

from gcode_lib.drivers.driver_interface import DriverInterface

log = logging.getLogger(__name__)


class FluidNCSerialDriver(DriverInterface):
    """
    Provide serial communication methods for FluidNC CNC controllers.

    This class acts purely as a transport layer.
    It transmits raw string commands and reads incoming line responses.

    Parameters
    ----------
    port : str
        The operating system serial port device identifier.
    baudrate : int, default=115200
        The serial communication speed in bits per second.
    safety_shutoff_command : str, default="\\x18"
        The character sequence required for immediate soft reset.
    rx_buffer_size : int, default=128
        The microcontroller hardware receive buffer limit in bytes.

    Attributes
    ----------
    REALTIME_COMMANDS : set of str
        The set of single-character real-time control commands.
    """

    REALTIME_COMMANDS = {"?", "~", "!", "\x18"}
    MAX_RX_BUFFER_BYTES = 4096

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        safety_shutoff_command: str = "\x18",
        rx_buffer_size: int = 128,
    ):
        assert baudrate > 0, "Baud rate must be positive."
        assert safety_shutoff_command, "Safety shutoff command must be set."

        self._port = port
        self._baudrate = baudrate
        self._safety_shutoff_command = safety_shutoff_command
        self._rx_buffer_size = rx_buffer_size

        self._serial: Optional[serial.Serial] = None
        self._rx_buffer = bytearray()

    @property
    def is_connected(self) -> bool:
        """
        Check if the serial port connection is active.

        Returns
        -------
        bool
            True if the serial port is open; False otherwise.
        """
        return self._serial is not None and self._serial.is_open

    @property
    def rx_buffer_size(self) -> int:
        """
        Get the microcontroller hardware receive buffer size.

        Returns
        -------
        int
            The hardware buffer capacity in bytes.
        """
        return self._rx_buffer_size

    @property
    def safety_shutoff_command(self) -> str:
        """
        Get the emergency shutoff command string.

        Returns
        -------
        str
            The command sequence required for immediate hardware stop.
        """
        return self._safety_shutoff_command

    def connect(self) -> None:
        """
        Open the serial port and initialize communication with FluidNC.

        Raises
        ------
        SerialException
            If the serial port cannot be opened.
        """
        if self.is_connected:
            log.warning("Serial connection on %s is already active.", self._port)
            return

        log.info(
            "Connecting to serial port %s at %d baud...", self._port, self._baudrate
        )
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=0,
                write_timeout=0.5,
                rtscts=False,
                dsrdtr=False,
            )

            # Prevent ESP32 from remaining in reset or bootloader mode
            self._serial.dtr = False
            self._serial.rts = False
            time.sleep(1.0)

            # Wake up hardware parser and clear input noise
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            self._serial.write(b"\r\n\r\n")
            time.sleep(0.1)
            self._serial.reset_input_buffer()
            self._rx_buffer.clear()

        except Exception as err:
            self._serial = None
            log.error("Failed to connect to serial port %s: %s", self._port, err)
            raise SerialException(f"Failed to connect to {self._port}") from err

    def close(self) -> None:
        """
        Close the serial port connection gracefully.
        """
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except Exception as err:
                log.warning("Error closing serial port %s: %s", self._port, err)
            finally:
                self._serial = None
                self._rx_buffer.clear()

    def terminate(self) -> None:
        """
        Close the serial port immediately.
        """
        self.close()

    def send_message(self, message: str, ensure_newline: bool = True) -> None:
        """
        Write a raw text payload string to the serial port.

        Parameters
        ----------
        message : str
            The text command string to transmit.
        ensure_newline : bool, default=True
            Set to True to append a newline character before transmission.

        Raises
        ------
        SerialException
            If the serial port is not connected or transmission fails.
        """
        if not self.is_connected or self._serial is None:
            log.error(
                "Cannot send message: Serial port %s is not connected.", self._port
            )
            raise SerialException("Serial port is not connected.")

        try:
            payload_str = message
            if ensure_newline and not payload_str.endswith("\n"):
                payload_str += "\n"

            self._serial.write(payload_str.encode("utf-8"))
            self._serial.flush()
        except SerialTimeoutException:
            log.error("Write timeout on %s. Buffer is full.", self._port)
            raise
        except (SerialException, OSError) as err:
            log.error("Hardware disconnected during write on %s: %s", self._port, err)
            self.close()
            raise SerialException(f"Write failure on port {self._port}") from err

    def send(self, message: str) -> None:
        """
        Route a command line and transmit it over serial.

        Parameters
        ----------
        message : str
            The command string to evaluate and transmit.
        """
        clean_msg = message.strip()
        is_realtime = len(clean_msg) == 1 and clean_msg in self.REALTIME_COMMANDS
        self.send_message(message, ensure_newline=not is_realtime)

    def read_message(self) -> Optional[str]:
        """
        Read the next complete response line from the serial buffer.

        Returns
        -------
        Optional[str]
            The received line string, or None if no full line exists.

        Raises
        ------
        SerialException
            If reading from the serial hardware fails.
        """
        if not self.is_connected or self._serial is None:
            return None

        try:
            in_waiting = self._serial.in_waiting
            if in_waiting > 0:
                self._rx_buffer.extend(self._serial.read(in_waiting))

            if len(self._rx_buffer) > self.MAX_RX_BUFFER_BYTES:
                log.warning("RX buffer threshold exceeded. Flushing corrupt bytes.")
                self._rx_buffer.clear()
                return None

            if b"\n" in self._rx_buffer:
                line_bytes, _, remaining = self._rx_buffer.partition(b"\n")
                self._rx_buffer = bytearray(remaining)
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if line:
                    return line

        except (SerialException, OSError) as err:
            log.error("Hardware disconnected during read on %s: %s", self._port, err)
            self.close()
            raise SerialException(f"Read failure on port {self._port}") from err

        return None

    def setup_reporting(self) -> None:
        """
        Send configuration commands to configure FluidNC status reporting.
        """
        self.send_message("$10=2", ensure_newline=True)

    def is_ack(self, response: str) -> bool:
        """
        Check if a response line is an acknowledgment signal.

        Parameters
        ----------
        response : str
            The raw response string received from hardware.

        Returns
        -------
        bool
            True if the line is 'ok' or starts with 'error:'; False otherwise.
        """
        resp = response.strip().lower()
        return resp == "ok" or resp.startswith("error:")
