import pytest
from unittest.mock import MagicMock, patch
from serial import SerialException
from gcode_lib import FluidNCSerialDriver

@pytest.fixture
def mock_serial():
    """Provides a mocked serial.Serial instance."""
    # Patch where serial.Serial is looked up inside your driver module
    with patch("gcode_lib.drivers.fluidnc.serial_driver.serial.Serial") as mock_serial_class:
        instance = MagicMock()
        instance.is_open = True
        mock_serial_class.return_value = instance
        yield instance

@pytest.fixture
def driver(mock_serial):
    """Provides a connected driver instance with DTR/Sleep bypassed for speed."""
    with patch("time.sleep"):  # Skip the 1.0s and 0.1s sleeps in connect()
        d = FluidNCSerialDriver(port="COM3")
        d.connect()
        return d

def test_initialization():
    driver = FluidNCSerialDriver(port="/dev/ttyUSB0", baudrate=115200)
    assert driver._port == "/dev/ttyUSB0"
    assert driver.safety_shutoff_command == "\x18"

def test_connect_sequence(driver, mock_serial):
    # Ensure ESP32 reset handling occurred
    assert mock_serial.dtr is False
    assert mock_serial.rts is False
    mock_serial.write.assert_called_with(b"\r\n\r\n")

def test_send_message_appends_newline(driver, mock_serial):
    driver.send_message("G0 X10")
    mock_serial.write.assert_called_with(b"G0 X10\n")

def test_send_message_realtime_no_newline(driver, mock_serial):
    driver.send_message("?", ensure_newline=False)
    mock_serial.write.assert_called_with(b"?")

def test_read_message_complete_line(driver, mock_serial):
    mock_serial.in_waiting = 10
    mock_serial.read.return_value = b"ok\n"
    
    msg = driver.read_message()
    assert msg == "ok"

def test_read_message_partial_buffering(driver, mock_serial):
    # First tick: Receive "o", no newline
    mock_serial.in_waiting = 1
    mock_serial.read.return_value = b"o"
    assert driver.read_message() is None

    # Second tick: Receive "k\n", completes line
    mock_serial.in_waiting = 2
    mock_serial.read.return_value = b"k\n"
    assert driver.read_message() == "ok"

def test_read_message_multiple_lines_in_buffer(driver, mock_serial):
    mock_serial.in_waiting = 15
    mock_serial.read.return_value = b"<Idle|WPos:0,0>\nok\n"
    
    # Should only pull the first line
    assert driver.read_message() == "<Idle|WPos:0,0>"
    
    # In waiting is now 0 on the hardware, but buffer still has data
    mock_serial.in_waiting = 0 
    assert driver.read_message() == "ok"

def test_disconnect_during_read_raises_error(driver, mock_serial):
    mock_serial.in_waiting = 1
    mock_serial.read.side_effect = SerialException("Device disconnected")
    
    with pytest.raises(SerialException):
        driver.read_message()
        
    assert driver._serial is None  # Should auto-close on hardware error
