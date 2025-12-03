import threading
import datetime
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from queue import Queue


class Message:
    _timestamp: datetime.Datetime
    _text: str
    _raw: any

    def __init__(self, arg: str | bytes):
        self.timestamp = datetime.datetime.now()

        if type(arg) == bytes:
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

    _exit_flag: Event
    _thread_executor: ThreadPoolExecutor
    _recv_queue: Queue
    _send_queue: Queue

    def __init__(self):

        # initialize defaults
        self._recv_queue = Queue()
        self._send_queue = Queue()
        self._exit_flag = Event().set()

    def __enter__(self):
        """used for context manager syntax"""
        pass

    def __exit__(self):
        """used for context manager syntax"""
        pass

    def _recv_thread(self, exit_flag: Event):
        """run a separate thread for receiving messages"""

        thread_name = threading.current_thread().name

        while not exit_flag.is_set():
            pass

    def _send_thread(self, exit_flag: Event):
        """run a separate thread for sending messages"""

        thread_name = threading.current_thread().name

        while not exit_flag.is_set():
            pass

    def open(self):
        """fallback for processes without context managers"""
        self.__enter__()

    def close(self):
        """fallback for processes without context managers"""
        self.__exit__()

    def send(self):
        """send any message text through a searate thread"""
        pass

    def recv(self):
        """receive any message text from a seperate thread"""
        pass
