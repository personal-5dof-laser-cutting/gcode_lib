import logging
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

        self._send_queue = Queue()
        self._recv_queue = Queue()
        self._serial = None

    def connect(self):
        """Establish a serial connection to the FluidNC controller."""
        if self._serial is not None and self._serial.is_open:
            log.warning("Serial connection on %s is already active.", self._port)
            return

        log.info("Connecting to serial port %s at %d baud...", self._port, self._baudrate)
        try:
            
            # Short timeout so read_message returns None non-blockingly when empty
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=0.05,
            )
            log.info("Connected to serial port %s", self._port)
        except Exception as e:
            self._serial = None
            log.error("Failed to connect to serial port %s: %s", self._port, e)
            raise

    def close(self):
        """Close the serial port connection gracefully."""
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
                log.info("Serial connection on %s closed gracefully.", self._port)
            except Exception as e:
                log.warning("Error closing serial port %s: %s", self._port, e)
            finally:
                self._serial = None

    def terminate(self):
        """Forcefully close the serial connection and clear local queues."""
        self.close()
        with self._send_queue.mutex:
            self._send_queue.queue.clear()
        with self._recv_queue.mutex:
            self._recv_queue.queue.clear()
        log.info("Serial driver terminated.")

    def queue_message(self, message: str):
        """
        Add a message to the send queue.

        Parameters
        ----------
        message : str
            The message to add.
        """
        self._send_queue.put(message)

    def send_message(self, message: str, respect_buffer: bool = True):
        """
        Send a message directly over serial, bypassing the send queue.

        Parameters
        ----------
        message : str
            The message to send.
        respect_buffer : bool, default True
            If True, wait for space in the remote buffer before sending.
        """
        if self._serial is None or not self._serial.is_open:
            log.error("Cannot send message: Serial port %s is not connected.", self._port)
            return

        try:
            payload = message.encode("utf-8")
            self._serial.write(payload)
            self._serial.flush()
        except Exception as e:
            log.error("Error writing to serial port %s: %s", self._port, e)
            raise

    def send(self, message: str):
        """
        Infer the send method based on the message type.

        Parameters
        ----------
        message : str
            The message to send.
        """
        if self._serial is None or not self._serial.is_open:
            log.error("Cannot send message: Serial port %s is not connected.", self._port)
            return

        # TODO: get a list of in-band commands from the corgi


    def read_message(self) -> Optional[str]:
        """
        Read a message from the receive buffer or serial interface.

        Returns
        -------
        str or None
            The message string if data is available, otherwise None.
        """
        if not self._recv_queue.empty():
            return self._recv_queue.get_nowait()

        # TODO: does this behaviour make sense?
        if self._serial is None or not self._serial.is_open:
            return None

        try:
            if self._serial.in_waiting > 0:
                line = self._serial.readline()
                if line:
                    return line.decode("utf-8", errors="replace").strip()
        except SerialException as e:
            log.error("Serial error while reading from %s: %s", self._port, e)
            return None
        except Exception as e:
            log.error("Unexpected error reading from serial port %s: %s", self._port, e)
            return None

        return None

    @property
    def safety_shutoff_command(self) -> str:
        """
        Get the safety shutoff command.

        Returns
        -------
        str
            The realtime command string.
        """
        return self._safety_shutoff_command
