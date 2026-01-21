import logging
import threading
import datetime
import time
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from websockets.sync.client import connect, ClientConnection
from websockets.exceptions import ConnectionClosedOK
from typing import Any

log = logging.getLogger(__name__)


class GCodeInterface:
    """send and receive messages through websockets without blocking the main thread"""

    _socket: ClientConnection
    _address: str
    _exit_flag: Event
    _thread_executor: ThreadPoolExecutor
    _recv_queue: Queue
    _send_queue: Queue
    _message_blacklist: list[str]

    def __init__(self, address: str, message_blacklist: list[str] = list()):
        # initialize defaults
        self._recv_queue = Queue()
        self._send_queue = Queue()
        self._exit_flag = Event()
        self._exit_flag.set()
        self._message_blacklist = message_blacklist

        self._address = address
        if not self._address.startswith("ws://"):
            self._address = f"ws://{address}"

        log.debug(f"% Initialized GCodeInterface for {self._address}")

    def __enter__(self):
        """used for context manager syntax"""

        log.info(f"= Connecting to {self._address}...")

        # purge lingering messages
        self._recv_queue = Queue()
        self._send_queue = Queue()

        try:
            # connect to websocket
            self._socket = connect(self._address)
            log.info("% Successfully connected to websocket.")
        except Exception as e:
            log.error(f"! Failed to connect to {self._address}: {e}")
            raise

        # start listening and sending threads
        self._exit_flag.clear()
        self._thread_executor = ThreadPoolExecutor(max_workers=2)
        self._thread_executor.submit(self._recv_thread)
        self._thread_executor.submit(self._send_thread)

        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any):
        """used for context manager syntax"""
        self._exit_flag.set()
        # INFO: this unblocks the get()
        self._send_queue.put("CLOSE")

        try:
            self._socket.close()
        except Exception as e:
            log.warning(f"! Error during socket closure: {e}")

        self._thread_executor.shutdown(wait=True)
        log.debug("% Thread executor shut down successfully.")

    def _recv_thread(self):
        """run a separate thread for receiving messages"""

        thread_name = threading.current_thread().name
        log.debug(f"% Receiver thread [{thread_name}] started.")

        while not self._exit_flag.is_set():
            try:
                response = self._socket.recv()

                if not response in self._message_blacklist:
                    self._recv_queue.put(response)
                    log.debug(f"< Message received: {response}")
                else:
                    log.debug(f"% Message iggnored: {response}")

            except ConnectionClosedOK:
                self._exit_flag.set()
                log.info("% Websocket connection closed normally.")
                break

            except Exception as e:
                log.exception(f"! Unexpected error in recv thread: {e}")
                self._exit_flag.set()
                break

    def _send_thread(self):
        """run a separate thread for sending messages"""

        thread_name = threading.current_thread().name
        log.debug(f"% Sender thread [{thread_name}] started.")

        while not self._exit_flag.is_set():
            try:
                message = self._send_queue.get()

                if message == "CLOSE":
                    log.debug("% Received internal CLOSE signal for sender thread.")
                    self._send_queue.task_done()
                    break

                self._socket.send(message)
                log.debug(f"> Message sent: {message.strip()}")
                self._send_queue.task_done()
            except Exception as e:
                log.error(f"! Exception in send thread [{thread_name}]: {e}, closing")
                self._exit_flag.set()

    def open(self):
        """fallback for processes without context managers"""
        return self.__enter__()

    def close(self):
        """fallback for processes without context managers"""
        return self.__exit__(exc_type="manual", exc_value=None, traceback=None)

    def send(self, message: str):
        """send any message text through a searate thread"""

        message = message.strip() + "\n"
        log.debug(f"> Queueing message: {message.strip()}")

        self._send_queue.put(message)

    def recv(self, timeout: float = None):
        """receive any message text from a separate thread"""
        try:
            if timeout is None:
                response = self._recv_queue.get_nowait()
            else:
                response = self._recv_queue.get(timeout=timeout)

            if isinstance(response, bytes):
                response = response.decode().strip()

            self._recv_queue.task_done()

            log.debug(f"< Chunk received: {response}")
            return response

        except:
            return None

    def send_and_recv(
        self, message: str, delimiter: str = "ok", recv_retries: int = 64
    ):
        """Send a message and read the response until the delimiter is found."""

        purged_count = 0
        while self.recv():
            purged_count += 1
        if purged_count > 0:
            log.debug(f"% Purged {purged_count} lingering messages from queue.")

        self.send(message)

        full_response = []
        found_delimiter = False

        while recv_retries > 0:
            response = self.recv(timeout=1.0)

            if not response:
                log.debug(f"Received empty response ({recv_retries} retries remaining.)")
                recv_retries -= 1

            if response:
                full_response.append(response)

                if delimiter.lower() in response.lower():
                    log.debug("% Delimiter found.")
                    found_delimiter = True
                    break
            else:
                continue

        combined_result = "\n".join(full_response)

        if not found_delimiter:
            log.warning(
                f"! Timeout waiting for delimiter '{delimiter}'. "
                f"! Retries exhausted ({recv_retries}s). "
                f"! Partial response: {combined_result.strip()}"
            )
        else:
            log.debug(f"Complete response: {combined_result.strip()}")

        return combined_result

    def ping(self, message: str = "M115", timeout: float = 2.0) -> bool:
        """
        Briefly checks if the connection is alive.
        If closed, it opens and closes it. If already open, it just sends the test.
        """
        # Track if we opened it just for this ping so we know whether to close it
        was_already_open = not self._exit_flag.is_set()

        try:
            if not was_already_open:
                log.debug("% Ping: Interface not open. Opening temporary connection.")
                self.open()

            response = self.send_and_recv(message)

            if response and len(response.strip()) > 0:
                log.info(f"< Ping successful: Received response.")
                return True

            log.warning("! Ping failed: No response received.")
            return False

        except Exception as e:
            log.error(f"! Ping failed with exception: {e}")
            return False
        finally:
            if not was_already_open:
                log.debug("% Ping: Closing temporary connection.")
                self.close()
