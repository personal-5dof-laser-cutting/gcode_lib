import pytest
from unittest.mock import MagicMock, patch, call
from serial import SerialException

from gcode_lib.drivers.fluidnc.serial_driver import FluidNCSerialDriver


@pytest.fixture
def mock_serial():
    """Provide a mocked serial.Serial instance."""
    with patch(
        "gcode_lib.drivers.fluidnc.serial_driver.serial.Serial"
    ) as mock_serial_class:
        instance = MagicMock()
        instance.is_open = True
        mock_serial_class.return_value = instance
        yield instance


@pytest.fixture
def driver(mock_serial):
    """Provide a connected driver instance with hardware delays bypassed."""
    with patch("time.sleep"):
        d = FluidNCSerialDriver(port="COM3")
        d.connect()
        return d


# -----------------------------------------------------------------------------
# Initialization & Interface Contract Tests
# -----------------------------------------------------------------------------


def test_initialization():
    driver = FluidNCSerialDriver(port="/dev/ttyUSB0", baudrate=115200)
    assert driver._port == "/dev/ttyUSB0"
    assert driver.safety_shutoff_command == "\x18"
    assert driver.rx_buffer_size == 128
    assert driver.is_connected is False


def test_is_connected_property(driver, mock_serial):
    assert driver.is_connected is True
    mock_serial.is_open = False
    assert driver.is_connected is False


def test_is_ack_evaluation(driver):
    assert driver.is_ack("ok") is True
    assert driver.is_ack("OK") is True
    assert driver.is_ack("error: 20") is True
    assert driver.is_ack("<Idle|MPos:0,0,0>") is False


# -----------------------------------------------------------------------------
# Connection Lifecycle Tests
# -----------------------------------------------------------------------------


def test_connect_sequence(driver, mock_serial):
    assert mock_serial.dtr is False
    assert mock_serial.rts is False
    mock_serial.write.assert_called_with(b"\r\n\r\n")


def test_connect_when_already_connected(driver, mock_serial):
    with patch("logging.Logger.warning") as mock_log:
        driver.connect()
        mock_log.assert_called_once()


def test_close_resets_connection_state(driver, mock_serial):
    driver.close()
    mock_serial.close.assert_called_once()
    assert driver._serial is None
    assert driver.is_connected is False


# -----------------------------------------------------------------------------
# Command Transmission Tests
# -----------------------------------------------------------------------------


def test_send_message_appends_newline(driver, mock_serial):
    driver.send_message("G0 X10", ensure_newline=True)
    mock_serial.write.assert_called_with(b"G0 X10\n")


def test_send_message_without_newline(driver, mock_serial):
    driver.send_message("?", ensure_newline=False)
    mock_serial.write.assert_called_with(b"?")


def test_send_routing_realtime_vs_standard(driver, mock_serial):
    # Real-time single character commands omit newline
    driver.send("?")
    mock_serial.write.assert_called_with(b"?")

    # Standard G-code appends newline
    driver.send("G21")
    mock_serial.write.assert_called_with(b"G21\n")


def test_setup_reporting(driver, mock_serial):
    driver.setup_reporting()
    mock_serial.write.assert_has_calls([
    call(b'$10=2\n'),
    call(b'$Report/Interval=0\n')
])


def test_send_message_disconnected_raises_exception():
    disconnected_driver = FluidNCSerialDriver(port="COM3")
    with pytest.raises(SerialException, match="not connected"):
        disconnected_driver.send_message("G0 X0")


# -----------------------------------------------------------------------------
# Receive Buffer & Error Resilience Tests
# -----------------------------------------------------------------------------


def test_read_message_complete_line(driver, mock_serial):
    mock_serial.in_waiting = 3
    mock_serial.read.return_value = b"ok\n"

    msg = driver.read_message()
    assert msg == "ok"


def test_read_message_partial_buffering(driver, mock_serial):
    mock_serial.in_waiting = 1
    mock_serial.read.return_value = b"o"
    assert driver.read_message() is None

    mock_serial.in_waiting = 2
    mock_serial.read.return_value = b"k\n"
    assert driver.read_message() == "ok"


def test_read_message_multiple_lines_in_buffer(driver, mock_serial):
    mock_serial.in_waiting = 18
    mock_serial.read.return_value = b"<Idle|WPos:0,0>\nok\n"

    assert driver.read_message() == "<Idle|WPos:0,0>"

    mock_serial.in_waiting = 0
    assert driver.read_message() == "ok"


def test_read_message_buffer_overflow_flushes_corrupt_data(driver, mock_serial):
    # Inject corrupt payload exceeding MAX_RX_BUFFER_BYTES (4096)
    mock_serial.in_waiting = 5000
    mock_serial.read.return_value = b"A" * 5000

    assert driver.read_message() is None
    assert len(driver._rx_buffer) == 0  # Buffer must be cleared


def test_read_message_replaces_invalid_utf8_bytes(driver, mock_serial):
    mock_serial.in_waiting = 6
    mock_serial.read.return_value = b"\xff\xfeok\n"

    # Should decode invalid UTF-8 bytes gracefully using replacement characters
    msg = driver.read_message()
    assert msg is not None
    assert "ok" in msg


def test_hardware_disconnect_during_read_raises_error(driver, mock_serial):
    mock_serial.in_waiting = 1
    mock_serial.read.side_effect = OSError("USB device unplugged")

    with pytest.raises(SerialException, match="Read failure"):
        driver.read_message()

    assert driver._serial is None
    assert driver.is_connected is False
