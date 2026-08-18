import logging
import socket
from typing import Optional

import websocket
from websocket import (
    WebSocketConnectionClosedException,
    WebSocketException,
    WebSocketTimeoutException,
)

from gcode_lib.drivers.driver_interface import DriverInterface

log = logging.getLogger(__name__)


class FluidNCWebsocketsDriver(DriverInterface):
    """
    Provide non-blocking WebSocket communication for FluidNC controllers.

    This class acts purely as a network transport layer.
    It transmits text commands and reads incoming line responses.

    Parameters
    ----------
    address : str
        The IP address or domain name of the controller.
    port : int
        The WebSocket server port number.
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
    MAX_RX_BUFFER_CHARS = 4096

    def __init__(
        self,
        address: str,
        port: int,
        safety_shutoff_command: str = "\x18",
        rx_buffer_size: int = 128,
    ):
        assert safety_shutoff_command, "Safety shutoff command must be set."
        assert port > 0, "Port must be a positive integer."

        self._address = address
        self._port = port
        self._safety_shutoff_command = safety_shutoff_command
        self._rx_buffer_size = rx_buffer_size

        self._ws: Optional[websocket.WebSocket] = None
        self._rx_buffer = ""

    @property
    def is_connected(self) -> bool:
        """
        Check if the WebSocket connection is active.

        Returns
        -------
        bool
            True if the WebSocket is connected; False otherwise.
        """
        return self._ws is not None and self._ws.connected

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
        Open the WebSocket connection to FluidNC.

        Raises
        ------
        WebSocketException
            If the network connection fails.
        """
        if self.is_connected:
            log.warning("WebSocket connection is already active.")
            return

        address = self._address
        if not (address.startswith("ws://") or address.startswith("wss://")):
            url = f"ws://{address}:{self._port}"
        else:
            url = f"{address}:{self._port}"

        log.info("Connecting to FluidNC WebSocket at %s...", url)
        try:
            ws = websocket.WebSocket()
            ws.connect(url, timeout=2.0)
            ws.settimeout(0.05)

            self._ws = ws
            self._rx_buffer = ""
            log.info("Connected to FluidNC WebSocket at %s", url)

        except Exception as err:
            self.close()
            log.error("Failed to connect to WebSocket at %s: %s", url, err)
            raise WebSocketException(f"Failed to connect to {url}") from err

    def close(self) -> None:
        """
        Close the WebSocket connection gracefully via standard close handshake.
        """
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception as err:
                log.warning("Error closing WebSocket connection: %s", err)
                self.terminate()
            finally:
                self._ws = None
                self._rx_buffer = ""

    def terminate(self) -> None:
        """
        Force close the WebSocket connection immediately without waiting for handshake.
        """
        if self._ws is not None:
            try:
                # Drop the raw socket immediately at the TCP transport layer
                if hasattr(self._ws, "sock") and self._ws.sock is not None:
                    import socket

                    try:
                        # SHUT_RDWR disables both sends and receives, unblocking pending reads
                        self._ws.sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self._ws.sock.close()

                self._ws.close()
            except Exception as err:
                log.warning("Error terminating WebSocket connection: %s", err)
            finally:
                self._ws = None
                self._rx_buffer = ""

    def send_message(self, message: str, ensure_newline: bool = True) -> None:
        """
        Write a raw text payload string directly to the WebSocket.

        Parameters
        ----------
        message : str
            The text command string to transmit.
        ensure_newline : bool, default=True
            Set to True to append a newline character before transmission.

        Raises
        ------
        WebSocketException
            If the socket is not connected or transmission fails.
        """
        if not self.is_connected or self._ws is None:
            log.error("Cannot send message: WebSocket is not connected.")
            raise WebSocketException("WebSocket is not connected.")

        try:
            payload_str = message
            if ensure_newline and not payload_str.endswith("\n"):
                payload_str += "\n"

            self._ws.send(payload_str)
        except (WebSocketException, socket.error, OSError) as err:
            log.error("Network error during write via WebSocket: %s", err)
            self.close()
            raise WebSocketException("Write failure on WebSocket connection.") from err

    def send(self, message: str) -> None:
        """
        Route a command line and transmit it over WebSocket.

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
        Read the next complete response line from the WebSocket buffer.

        Returns
        -------
        Optional[str]
            The received line string, or None if no full line exists.

        Raises
        ------
        WebSocketException
            If reading from the network connection fails.
        """
        if not self.is_connected or self._ws is None:
            return None

        # Process existing buffer content
        if "\n" in self._rx_buffer:
            line, _, remaining = self._rx_buffer.partition("\n")
            self._rx_buffer = remaining
            clean_line = line.strip()
            if clean_line:
                return clean_line

        try:
            data = self._ws.recv()
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")

            self._rx_buffer += data

            if len(self._rx_buffer) > self.MAX_RX_BUFFER_CHARS:
                log.warning("RX buffer threshold exceeded. Flushing corrupt buffer.")
                self._rx_buffer = ""
                return None

            if "\n" in self._rx_buffer:
                line, _, remaining = self._rx_buffer.partition("\n")
                self._rx_buffer = remaining
                clean_line = line.strip()
                if clean_line:
                    return clean_line

        except (WebSocketTimeoutException, socket.timeout, TimeoutError):
            pass
        except (
            WebSocketConnectionClosedException,
            WebSocketException,
            socket.error,
            OSError,
        ) as err:
            log.error("WebSocket error during read: %s", err)
            self.close()
            raise WebSocketException("Read failure on WebSocket connection.") from err

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
