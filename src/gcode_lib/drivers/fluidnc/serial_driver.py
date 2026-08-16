import logging
import time
from typing import Optional

import serial
from serial import SerialException, SerialTimeoutException

from gcode_lib.communication_interface import CommunicationInterface

log = logging.getLogger(__name__)


class HardwareDisconnectedError(Exception):
    """Raised when the hardware is abruptly disconnected."""

    pass


class FluidNCSerialDriver(CommunicationInterface):
    """
    Non-blocking serial communication driver for FluidNC.
    Acts purely as a transport pipe without managing state or queues.
    """

    # INFO: # Status (?), Cycle Start (~), Feed Hold (!), Soft Reset (\x18)
    REALTIME_COMMANDS = {"?", "~", "!", "\x18"}

    def __init__(
        self, port: str, baudrate: int = 115200, safety_shutoff_command: str = "\x18"
    ):
        assert baudrate > 0, "Baud rate must be positive."
        assert safety_shutoff_command, "Safety shutoff command must be set."

        self._port = port
        self._baudrate = baudrate
        self._safety_shutoff_command = safety_shutoff_command

        self._serial: Optional[serial.Serial] = None
        self._rx_buffer = bytearray()

    def connect(self):
        if self._serial is not None and self._serial.is_open:
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

            # Wake up GRBL/FluidNC parser and flush serial boot noise
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            self._serial.write(b"\r\n\r\n")
            time.sleep(0.1)
            self._serial.reset_input_buffer()
            self._rx_buffer.clear()

        except Exception as e:
            self._serial = None
            log.error("Failed to connect to serial port %s: %s", self._port, e)
            raise

    def close(self):
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except Exception as e:
                log.warning("Error closing serial port %s: %s", self._port, e)
            finally:
                self._serial = None
                self._rx_buffer.clear()

    def terminate(self):
        self.close()

    def send_message(self, message: str, append_newline: bool = True):
        """Write raw payload string directly to serial port."""
        if self._serial is None or not self._serial.is_open:
            log.error(
                "Cannot send message: Serial port %s is not connected.", self._port
            )
            raise HardwareDisconnectedError("Serial port is not connected.")

        try:
            payload_str = message
            if append_newline and not payload_str.endswith("\n"):
                payload_str += "\n"

            self._serial.write(payload_str.encode("utf-8"))
            self._serial.flush()
        except SerialTimeoutException:
            log.error("Write timeout on %s. Buffer might be full.", self._port)
            raise
        except SerialException as e:
            log.error("Hardware disconnected during write on %s: %s", self._port, e)
            self.close()
            raise HardwareDisconnectedError(f"Connection lost: {e}")

    def send(self, message: str):
        """
        Intelligently send a command.
        Infers if the message is a real-time command and skips the newline if so.
        """
        clean_msg = message.strip()
        is_realtime = len(clean_msg) == 1 and clean_msg in self.REALTIME_COMMANDS

        self.send_message(message, append_newline=not is_realtime)

    def read_message(self) -> Optional[str]:
        if self._serial is None or not self._serial.is_open:
            return None

        try:
            in_waiting = self._serial.in_waiting
            if in_waiting > 0:
                self._rx_buffer.extend(self._serial.read(in_waiting))

            if b"\n" in self._rx_buffer:
                line_bytes, _, remaining = self._rx_buffer.partition(b"\n")
                self._rx_buffer = bytearray(remaining)
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if line:
                    return line

        except OSError as e:
            log.error("Hardware disconnected during read on %s: %s", self._port, e)
            self.close()
            raise HardwareDisconnectedError(f"Connection lost: {e}")

        return None

    def setup_reporting(self):
        self.send_message("$10=2", append_newline=True)

    @property
    def safety_shutoff_command(self) -> str:
        return self._safety_shutoff_command
