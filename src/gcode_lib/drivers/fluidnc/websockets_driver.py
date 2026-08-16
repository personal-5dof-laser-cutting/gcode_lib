import logging
import socket
from typing import Optional

import websocket
from websocket import WebSocketException, WebSocketTimeoutException

from gcode_lib.drivers.driver_interface import DriverInterface

log = logging.getLogger(__name__)


class FluidNCWebsocketsDriver(DriverInterface):
    """
    Non-blocking WebSockets communication driver for FluidNC.
    Acts purely as a transport pipe without managing state or queues.
    """

    # INFO: # Status (?), Cycle Start (~), Feed Hold (!), Soft Reset (\x18)
    REALTIME_COMMANDS = {"?", "~", "!", "\x18"}

    def __init__(self, address: str, port: int, safety_shutoff_command: str = "\x18"):
        assert safety_shutoff_command, "Safety shutoff command must be set."

        self._address = address
        self._port = port
        self._safety_shutoff_command = safety_shutoff_command

        self._ws: Optional[websocket.WebSocket] = None
        self._rx_buffer = ""

    def connect(self):
        if self._ws is not None and self._ws.connected:
            log.warning("WebSocket connection is already active.")
            return

        address = self._address
        if not (address.startswith("ws://") or address.startswith("wss://")):
            url = f"ws://{address}:{self._port}"
        else:
            url = f"{address}:{self._port}"

        log.info("Connecting to FluidNC WebSocket at %s...", url)
        try:
            self._ws = websocket.WebSocket()
            self._ws.connect(url, timeout=2.0)

            # Short timeout so read_message returns None non-blockingly when empty
            self._ws.settimeout(0.05)
            self._rx_buffer = ""

            log.info("Connected to FluidNC WebSocket at %s", url)
        except Exception as e:
            self._ws = None
            log.error("Failed to connect to FluidNC WebSocket at %s: %s", url, e)
            raise

    def close(self):
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception as e:
                log.warning("Error closing WebSocket connection: %s", e)
            finally:
                self._ws = None
                self._rx_buffer = ""

    def terminate(self):
        self.close()

    def send_message(self, message: str, ensure_newline: bool = True):
        """Write raw payload string directly to WebSocket."""
        if self._ws is None or not self._ws.connected:
            log.error("Cannot send message: WebSocket is not connected.")
            raise WebSocketException("WebSocket is not connected.")

        try:
            payload_str = message
            if ensure_newline and not payload_str.endswith("\n"):
                payload_str += "\n"

            self._ws.send(payload_str)
        except Exception as e:
            log.error("Hardware disconnected during write via WebSocket: %s", e)
            self.close()
            raise

    def send(self, message: str):
        """
        Intelligently send a command.
        Infers if the message is a real-time command and skips the newline if so.
        """
        clean_msg = message.strip()
        is_realtime = len(clean_msg) == 1 and clean_msg in self.REALTIME_COMMANDS

        self.send_message(message, ensure_newline=not is_realtime)

    def read_message(self) -> Optional[str]:
        if self._ws is None or not self._ws.connected:
            return None

        # Check if we already have a complete line in the buffer
        if "\n" in self._rx_buffer:
            line, _, remaining = self._rx_buffer.partition("\n")
            self._rx_buffer = remaining
            clean_line = line.strip()
            if clean_line:
                return clean_line

        # No complete line buffered, try to read from WebSocket
        try:
            data = self._ws.recv()
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")

            self._rx_buffer += data

            # Process the newly appended buffer
            if "\n" in self._rx_buffer:
                line, _, remaining = self._rx_buffer.partition("\n")
                self._rx_buffer = remaining
                clean_line = line.strip()
                if clean_line:
                    return clean_line

        except (WebSocketTimeoutException, socket.timeout, TimeoutError):
            # Normal timeout for a non-blocking read operation
            pass
        except WebSocketException as e:
            log.error("WebSocket error while reading: %s", e)
            self.close()
            raise e
        except Exception as e:
            log.error("Unexpected hardware disconnect via WebSocket: %s", e)
            self.close()
            raise e

        return None

    def setup_reporting(self):
        self.send_message("$10=2", ensure_newline=True)

    @property
    def safety_shutoff_command(self) -> str:
        return self._safety_shutoff_command
