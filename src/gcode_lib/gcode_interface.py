import threading
import datetime
import time
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from websockets.sync.client import connect, ClientConnection
from websockets.exceptions import ConnectionClosedOK
from typing import Any


class GCodeInterface:
    """send and receive messages through websockets without blocking the main thread"""

    _socket: ClientConnection
    _address: str
    _exit_flag: Event
    _thread_executor: ThreadPoolExecutor
    _recv_queue: Queue
    _send_queue: Queue

    def __init__(self, address: str):
        # initialize defaults
        self._recv_queue = Queue()
        self._send_queue = Queue()
        self._exit_flag = Event()
        self._exit_flag.set()

        self._address = address
        if not self._address.startswith("ws://"):
            self._address = f"ws://{address}"

    def __enter__(self):
        """used for context manager syntax"""

        # purge lingering messages
        self._recv_queue = Queue()
        self._send_queue = Queue()

        # connect to websocket
        self._socket = connect(self._address)

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
            print(f"Warning closing socket: {e}")

        self._thread_executor.shutdown(wait=True)

    def _recv_thread(self):
        """run a separate thread for receiving messages"""

        thread_name = threading.current_thread().name

        while not self._exit_flag.is_set():
            try:
                response = self._socket.recv()
                self._recv_queue.put(response)

            except ConnectionClosedOK:
                self._exit_flag.set()
                break

            except Exception as e:
                print(f"Exception in recv thread [{thread_name}]: {e}, closing")
                self._exit_flag.set()
                break

    def _send_thread(self):
        """run a separate thread for sending messages"""

        thread_name = threading.current_thread().name

        while not self._exit_flag.is_set():
            try:
                message = self._send_queue.get()

                if message == "CLOSE":
                    self._send_queue.task_done()
                    break

                self._socket.send(message)
                self._send_queue.task_done()
            except Exception as e:
                print(f"Exception in send thread [{thread_name}]: {e}, closing")
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

            return response

        except:
            return None

    def send_and_recv(self, message, delimiter="ok"):
        """send a message and read the response"""

        # clear recv queue

        while self.recv():
            pass

        self.send(message)

        response = None
        full_response = []

        while True:
            response = self.recv(timeout=1)
            full_response.append(response)

            if not response:
                continue

            if delimiter in response.lower():
                break

        return "\n".join(full_response)

    def ping(self, message: str = "\n"):
        """briefly open the connection and send a test message"""

        try:
            self.open()
            self.send(message)

            time.sleep(1)

            message = self.recv()
            if message:
                self.close()
                return True

        except TimeoutError:
            pass
        finally:
            self.close()

        return False
