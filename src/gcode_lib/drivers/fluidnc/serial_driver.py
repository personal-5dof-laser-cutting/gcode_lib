import logging
import time
from typing import Optional

import serial
from serial import SerialException

from gcode_lib.communication_interface import CommunicationInterface

log = logging.getLogger(__name__)


# TODO: CommunicationInterface
class FluidNCSerialDriver:
    """
    Non-blocking serial communication driver for FluidNC.
    Acts purely as a transport pipe without managing state or queues.
    """

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

        log.debug(
            "FluidNCSerialDriver initialized for port=%s, baudrate=%d, safety_shutoff_command=%r",
            port,
            baudrate,
            safety_shutoff_command,
        )

    def connect(self):
        """Establish a serial connection to the FluidNC controller."""
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

            # Allow ESP32 a moment to finish hardware reset after DTR toggle
            time.sleep(1.0)

            # Wake up GRBL/FluidNC parser and flush serial boot noise
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            self._serial.write(b"\r\n\r\n")
            time.sleep(0.1)
            self._serial.reset_input_buffer()
            self._rx_buffer.clear()

            log.info(
                "Connected to serial port %s (DTR/RTS cleared, wake-up sent)",
                self._port,
            )
        except Exception as e:
            self._serial = None
            log.error("Failed to connect to serial port %s: %s", self._port, e)
            raise

    def close(self):
        """Close the serial port connection gracefully."""
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    log.debug("Closing serial port %s...", self._port)
                    self._serial.close()
                log.info("Serial connection on %s closed gracefully.", self._port)
            except Exception as e:
                log.warning("Error closing serial port %s: %s", self._port, e)
            finally:
                self._serial = None
                self._rx_buffer.clear()

    def terminate(self):
        """Forcefully close the serial connection."""
        log.warning("Terminating serial driver on %s...", self._port)
        self.close()

    def send_message(self, message: str, respect_buffer: bool = True):
        """Write raw payload string directly to serial port."""
        if self._serial is None or not self._serial.is_open:
            log.error(
                "Cannot send message: Serial port %s is not connected.", self._port
            )
            return

        try:
            # Ensure line ending for G-code if not present and not a real-time command
            payload_str = message
            if respect_buffer and not payload_str.endswith("\n"):
                payload_str += "\n"

            log.debug(
                "Writing bytes to serial %s: %r",
                self._port,
                payload_str,
            )
            self._serial.write(payload_str.encode("utf-8"))
            self._serial.flush()
        except Exception as e:
            log.error("Error writing to serial port %s: %s", self._port, e)
            raise

    def send(self, message: str):
        """Forward send call directly to send_message."""
        self.send_message(message, respect_buffer=True)

    def read_message(self) -> Optional[str]:
        """
        Non-blocking read. Drains available serial bytes into an internal buffer
        and returns complete lines one at a time.
        """
        if self._serial is None or not self._serial.is_open:
            return None

        try:
            # 1. Read all waiting raw bytes into our stream buffer
            in_waiting = self._serial.in_waiting
            if in_waiting > 0:
                self._rx_buffer.extend(self._serial.read(in_waiting))

            # 2. Extract the first complete line if a newline exists
            if b"\n" in self._rx_buffer:
                line_bytes, _, remaining = self._rx_buffer.partition(b"\n")
                self._rx_buffer = bytearray(remaining)
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if line:  # Filter out empty blank lines
                    log.debug("Read line from serial %s: %r", self._port, line)
                    return line

        except SerialException as e:
            log.error("Serial error while reading from %s: %s", self._port, e)
            return None
        except Exception as e:
            log.error("Unexpected error reading from serial port %s: %s", self._port, e)
            return None

        return None

    def get_state(self) -> Optional[str]:
        """Send asynchronous status request '?' without blocking."""
        log.debug("Sending real-time state query '?' to serial %s", self._port)
        self.send_message("?", respect_buffer=False)
        return None

    def setup_reporting(self):
        """Configure status reporting mask ($10=2)."""
        log.info("Configuring FluidNC status reporting mask ($10=2)...")
        self.send_message("$10=2", respect_buffer=False)

    @property
    def safety_shutoff_command(self) -> str:
        return self._safety_shutoff_command
