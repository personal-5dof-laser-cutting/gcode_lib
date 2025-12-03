class GCodeInterface:

    def __init__(self):
        pass

    def __enter__(self):
        """used for context manager syntax"""
        pass

    def __exit__(self):
        """used for context manager syntax"""
        pass

    def open(self):
        """fallback for processes without context managers"""
        self.__enter__()

    def close(self):
        """fallback for processes without context managers"""
        self.__exit__()

    def send(self):
        """send any message through a searate thread"""
        pass

    def recv(self):
        """receive any message from a seperate thread"""
        pass
