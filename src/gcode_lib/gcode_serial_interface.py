import serial
import time
from typing import Any, Optional

class Gcode_Serial:
    def __init__(self, port: str, baudrate: int) -> None:
        self._port = port
        self._baudrate = baudrate
        self._conn: Optional[serial.Serial] = None

    def __enter__(self):
        self._conn = serial.Serial(self._port, self._baudrate, timeout=1)
        self._conn.dtr = False
        self._conn.rts = False

        print("Waiting for FluidNC to stabilize...")

        time.sleep(5)

        self._conn.write(b"\r\n\r\n")
        time.sleep(5)

        if self._conn.in_waiting:
            self._conn.read(self._conn.in_waiting)

        print("FluidNC is clear and ready.")
        return self

    def send_command(self, cmd: str):
        if not self._conn:
            return

        full_cmd = f"{cmd.strip()}\n".encode("utf-8")
        self._conn.write(full_cmd)

        response_lines = []
        while True:
            line = self._conn.readline().decode("utf-8").strip()
            if not line:
                break  # Timeout
            response_lines.append(line)
            if line.lower() == "ok":
                break

        return response_lines

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any):
        if self._conn:
            self._conn.close()
