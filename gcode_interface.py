import threading
import datetime
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from websockets.sync.client import connect, ClientConnection
from typing import Any


class Message:
    _timestamp: datetime.datetime
    _text: str
    _raw: Any

    def __init__(self, arg: str | bytes):
        self.timestamp = datetime.datetime.now()

        if isinstance(arg, bytes):
            self.raw = arg
            self.text = arg.decode()
            return

        try:
            self.text = str(arg)
            self.raw = arg
        except ValueError:
            raise NotImplementedError(f"Received {type(arg)}")

    @property
    def text(self):
        return self._text

    @property
    def raw(self):
        return self._raw

    @property
    def timestamp(self):
        return self._timestamp


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
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._executor.submit(self._recv_thread)
        self._executor.submit(self._send_thread)

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any):
        """used for context manager syntax"""
        self._exit_flag.set()
        # INFO: this unblocks the get()
        self._send_queue.put("CLOSE")

        try:
            self._socket.close()
        except Exception as e:
            print(f"Warning closing socket: {e}")

        self._executor.shutdown(wait=True)

    def _recv_thread(self):
        """run a separate thread for receiving messages"""

        thread_name = threading.current_thread().name

        while not self._exit_flag.is_set():
            try:
                message_content_raw = self._socket.recv()
                message = Message(message_content_raw)
                self._recv_queue.put(message)
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

                self._socket.send(message.text)  # WARN: not sure about the type here
                self._send_queue.task_done()
            except Exception as e:
                print(f"Exception in send thread [{thread_name}]: {e}, closing")
                self._exit_flag.set()

    def open(self):
        """fallback for processes without context managers"""
        self.__enter__()

    def close(self):
        """fallback for processes without context managers"""
        self.__exit__()

    def send(self, message: Message | Any):
        """send any message text through a searate thread"""

        if not isinstance(message, Message):
            message = Message(message)

        self._send_queue.put(message)

    def recv(self):
        """receive any message text from a seperate thread"""
        return self._recv_queue.get()

if __name__ == "__main__":
    with GCodeInterface("ws://192.168.0.1") as gif:
        pass
