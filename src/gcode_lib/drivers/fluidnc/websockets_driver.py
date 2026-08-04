import logging
from queue import Queue
import socket
from typing import Optional

import websocket
from websocket import WebSocketException, WebSocketTimeoutException

from gcode_lib.communication_interface import CommunicationInterface

log = logging.getLogger(__name__)


class FluidNCWebsocketsDriver(CommunicationInterface):
    """WebSockets communication driver for FluidNC."""

    _address: str
    _port: int
    _safety_shutoff_command: str
    _send_queue: Queue
    _recv_queue: Queue
    _ws: Optional[websocket.WebSocket]

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

        self._send_queue = Queue()
        self._recv_queue = Queue()
        self._ws = None

    def connect(self):
        """Establish a WebSocket connection to the FluidNC controller."""
        if self._ws is not None:
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
            log.info("Connected to FluidNC WebSocket at %s", url)
        except Exception as e:
            self._ws = None
            log.error("Failed to connect to FluidNC WebSocket at %s: %s", url, e)
            raise

    def close(self):
        """Close the WebSocket connection gracefully."""
        if self._ws is not None:
            try:
                self._ws.close()
                log.info("WebSocket connection closed gracefully.")
            except Exception as e:
                log.warning("Error closing WebSocket connection: %s", e)
            finally:
                self._ws = None

    def terminate(self):
        """Forcefully close the connection and clear local queues."""
        self.close()
        with self._send_queue.mutex:
            self._send_queue.queue.clear()
        with self._recv_queue.mutex:
            self._recv_queue.queue.clear()
        log.info("WebSocket driver terminated.")

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
        Send a message directly over the WebSocket, bypassing the send queue.

        Parameters
        ----------
        message : str
            The message to send.
        respect_buffer : bool, default True
            If True, wait for space in the remote buffer before sending.
        """
        if self._ws is None:
            log.error("Cannot send message: WebSocket is not connected.")
            return

        try:
            self._ws.send(message)
        except Exception as e:
            log.error("Error sending message via WebSocket: %s", e)
            raise

    def send(self, message: str):
        """
        Infer the send method based on the message type.

        Parameters
        ----------
        message : str
            The message to send.
        """
        if self._ws is None:
            log.error("Cannot send message: WebSocket is not connected.")
            return

        # TODO: get a list of in-band commands from the corgi

    def read_message(self) -> Optional[str]:
        """
        Read a message from the receive buffer or the WebSocket.

        Returns
        -------
        str or None
            The message if data is available, otherwise None.
        """
        if not self._recv_queue.empty():
            return self._recv_queue.get_nowait()

        # TODO: does this behaviour make sense?
        if self._ws is None:
            return None

        try:
            data = self._ws.recv()
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return data
        except (WebSocketTimeoutException, socket.timeout, TimeoutError):
            return None
        except WebSocketException as e:
            log.error("WebSocket error while reading: %s", e)
            return None
        except Exception as e:
            log.error("Unexpected error reading from WebSocket: %s", e)
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
