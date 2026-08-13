import logging
import time
from queue import Queue
from typing import Optional

import serial
from serial import SerialException

from gcode_lib.communication_interface import CommunicationInterface

log = logging.getLogger(__name__)


class FluidNCSerialDriver(CommunicationInterface):
    """Serial communication driver for FluidNC."""

    _port: str
    _baudrate: int
    _safety_shutoff_command: str
    _send_queue: Queue
    _recv_queue: Queue
    _serial: Optional[serial.Serial]

    def __init__(
        self, port: str, baudrate: int = 115200, safety_shutoff_command: str = "\x18"
    ):
        assert baudrate > 0, "Baud rate must be positive."
        assert safety_shutoff_command, "Safety shutoff command must be set."

        self._port = port
        self._baudrate = baudrate
        self._safety_shutoff_command = safety_shutoff_command

        self._send_queue = Queue()
        self._recv_queue = Queue()
        self._serial = None

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
                timeout=0.1,
                rtscts=False,
                dsrdtr=False,
            )

            # INFO: Prevent ESP32 from remaining in reset or bootloader mode
            self._serial.dtr = False
            self._serial.rts = False

            time.sleep(1.0)

            # INFO: Wake up GRBL/FluidNC parser and flush serial boot noise
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            self._serial.write(b"\r\n\r\n")
            time.sleep(0.1)
            self._serial.reset_input_buffer()

            log.info("Connected to serial port %s (DTR/RTS cleared, wake-up sent)", self._port)
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

    def terminate(self):
        """Forcefully close the serial connection and clear local queues."""
        log.warning("Terminating serial driver on %s and clearing queues...", self._port)
        self.close()
        with self._send_queue.mutex:
            self._send_queue.queue.clear()
        with self._recv_queue.mutex:
            self._recv_queue.queue.clear()
        log.info("Serial driver terminated.")

    def queue_message(self, message: str):
        log.debug("Queueing message for serial send: %r", message)
        self._send_queue.put(message)

    def send_message(self, message: str, respect_buffer: bool = True):
        if self._serial is None or not self._serial.is_open:
            log.error(
                "Cannot send message: Serial port %s is not connected.", self._port
            )
            return

        try:
            log.debug(
                "Writing payload directly to serial %s (respect_buffer=%s): %r",
                self._port,
                respect_buffer,
                message,
            )
            payload = message.encode("utf-8")
            self._serial.write(payload)
            self._serial.flush()
        except Exception as e:
            log.error("Error writing to serial port %s: %s", self._port, e)
            raise

    def send(self, message: str):
        if self._serial is None or not self._serial.is_open:
            log.error(
                "Cannot send message: Serial port %s is not connected.", self._port
            )
            return

        log.debug("Inferred send called with message: %r", message)
        pass

    def read_message(self) -> Optional[str]:
        if not self._recv_queue.empty():
            msg = self._recv_queue.get_nowait()
            log.debug("Read message from driver internal recv queue: %r", msg)
            return msg

        if self._serial is None or not self._serial.is_open:
            return None

        try:
            if self._serial.in_waiting > 0:
                line_bytes = self._serial.readline()
                if line_bytes:
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    log.debug("Read line directly from serial %s: %r", self._port, line)
                    return line
        except SerialException as e:
            log.error("Serial error while reading from %s: %s", self._port, e)
            return None
        except Exception as e:
            log.error("Unexpected error reading from serial port %s: %s", self._port, e)
            return None

        return None

    def get_state(self) -> Optional[str]:
        if self._serial is None or not self._serial.is_open:
            log.error("Cannot query state: Serial port %s is not connected.", self._port)
            return None

        try:
            log.debug("Sending real-time state query '?' to serial %s", self._port)
            self._serial.write(b"?")
            self._serial.flush()
        except Exception as e:
            log.error("Failed to send state query: %s", e)
            return None

        timeout_time = time.time() + 0.5
        while time.time() < timeout_time:
            try:
                if self._serial.in_waiting > 0:
                    line = (
                        self._serial.readline()
                        .decode("utf-8", errors="replace")
                        .strip()
                    )
                    if line.startswith("<") and line.endswith(">"):
                        log.debug("Received state response from serial %s: %r", self._port, line)
                        return line
                    elif line:
                        log.debug(
                            "Intercepted non-state response during get_state, queueing: %r",
                            line,
                        )
                        self._recv_queue.put(line)
            except SerialException as e:
                log.error("Serial error while waiting for state: %s", e)
                break
            except Exception as e:
                log.error("Unexpected error waiting for state: %s", e)
                break

            time.sleep(0.01)

        log.warning("Timeout waiting for state response from FluidNC on %s.", self._port)
        return None

    def setup_reporting(self):
        log.info("Configuring FluidNC status reporting mask ($10=2)...")
        log.debug("Sending setup command payload: %r", "$10=2\n")
        self.send_message("$10=2\n", respect_buffer=False)

    @property
    def safety_shutoff_command(self) -> str:
        return self._safety_shutoff_command
