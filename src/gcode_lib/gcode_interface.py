from abc import ABC, abstractmethod

class CommunicationInterface(ABC):
    @abstractmethod
    def connect(self): pass
    @abstractmethod
    def close(self): pass
    @abstractmethod
    def terminate(self): pass
    @abstractmethod
    def queue_message(self, message: string): pass
    @abstractmethod
    def send(self, message: string): pass
    @abstractmethod
    def read_line(self) -> str: pass

class FluidNCSerialDriver(CommunicationInterface):

    _port: str
    _baudrate: int

    def __init__(self, port: str, baudrate: int = 115200):
        self._port = port
        self._baudrate = baudrate

    def connect(self):
        pass

    def close(self):
        pass

    def terminate(self):
        pass

    def queue_message(self, message: str):
        pass

    def send(self, message: str):
        pass

    def read_line(self, message: str):
        pass

class FluidNCWebsocketsDriver(CommunicationInterface):

    _address: str
    _port: int

    def __init__(self, address: str, port: int):
        self._address = address
        self._port = port

    def connect(self):
        pass

    def close(self):
        pass

    def terminate(self):
        pass

    def queue_message(self, message: str):
        pass

    def send(self, message: str):
        pass

    def read_line(self, message: str):
        pass

class CommunicationWorker:

    def __init__(self) -> None:
        pass

class CommunicationInterface:

    def __init__(self) -> None:
        pass
