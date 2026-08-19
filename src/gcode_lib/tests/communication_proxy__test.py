import queue
import time
from unittest.mock import MagicMock

import pytest

from gcode_lib.communication_worker import CommunicationWorker
import gcode_lib.ipc_commands as ipc


@pytest.fixture
def mock_driver():
    """Provides a fully compliant mock DriverInterface instance."""
    driver = MagicMock()
    driver.safety_shutoff_command = "\x18"
    driver.rx_buffer_size = 128
    driver.is_connected = True
    driver.read_message.return_value = None
    driver.is_ack.side_effect = lambda line: line == "ok" or line.startswith("error:")
    return driver


@pytest.fixture
def worker(mock_driver):
    """Provides a worker configured with standard thread-safe queues."""
    w = CommunicationWorker(driver=mock_driver, timeout_sec=0.1, buffer_size=128)
    w.cmd_queue = queue.Queue()
    w.response_queue = queue.Queue()
    return w


# -----------------------------------------------------------------------------
# Lifecycle & Startup Tests
# -----------------------------------------------------------------------------


def test_successful_connect_and_shutdown(worker, mock_driver):
    worker.cmd_queue.put(ipc.Shutdown())
    worker.run()

    assert worker.ready_event.is_set()
    mock_driver.connect.assert_called_once()
    mock_driver.close.assert_called_once()


def test_connect_failure_notifies_proxy(worker, mock_driver):
    mock_driver.connect.side_effect = Exception("Serial port locked")

    worker.run()

    assert isinstance(worker.response_queue.get(), ipc.HardwareTimeout)
    mock_driver.close.assert_called_once()


# -----------------------------------------------------------------------------
# Buffer & Command Tracking Tests
# -----------------------------------------------------------------------------


def test_buffer_management(worker, mock_driver):
    worker.cmd_queue.put(ipc.QueueMessage("G0 X10"))
    worker.cmd_queue.put(ipc.Shutdown())

    worker.run()

    # "G0 X10\n" = 7 bytes
    mock_driver.send.assert_called_with("G0 X10")
    assert worker.bytes_in_buffer == 7
    assert len(worker._pending_line_lengths) == 1


def test_ack_frees_buffer(worker, mock_driver):
    worker._pending_line_lengths.append(10)

    mock_driver.read_message.side_effect = ["ok", None, None]

    worker.cmd_queue.put(ipc.Heartbeat())
    worker.cmd_queue.put(ipc.Shutdown())

    worker.run()

    assert worker.bytes_in_buffer == 0
    assert worker.response_queue.get() == "ok"


def test_buffer_capacity_holds_overflowing_commands(worker, mock_driver):
    # Set tiny buffer size to trigger capacity hold easily
    worker.buffer_size = 10
    worker._pending_line_lengths.append(8)  # Only 2 bytes remaining

    # Attempting to queue a 7 byte command ("G0 X10\n") should hold
    worker.cmd_queue.put(ipc.QueueMessage("G0 X10"))
    worker.cmd_queue.put(ipc.Shutdown())

    worker.run()

    # Command should not be sent because buffer space (2 bytes) < 7 bytes
    mock_driver.send.assert_not_called()


# -----------------------------------------------------------------------------
# Fault & Watchdog Tests
# -----------------------------------------------------------------------------


def test_hardware_disconnect_handling(worker, mock_driver):
    mock_driver.read_message.side_effect = Exception("Unplugged")

    worker.run()

    assert isinstance(worker.response_queue.get(), ipc.HardwareTimeout)
    mock_driver.close.assert_called_once()


def test_watchdog_triggers_estop(worker, mock_driver):
    worker.cmd_queue.put(ipc.Heartbeat())

    original_monotonic = time.monotonic

    def time_travel():
        return original_monotonic() + 1.0  # Jump 1 second forward

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            time,
            "monotonic",
            MagicMock(
                side_effect=[
                    original_monotonic(),  # last_heartbeat init
                    original_monotonic(),  # heartbeat receive timestamp
                    time_travel(),  # watchdog check triggers
                ]
            ),
        )
        worker.run()

    # Safety shutoff uses updated ensure_newline parameter
    mock_driver.send_message.assert_called_with("\x18", ensure_newline=False)
    mock_driver.terminate.assert_called_once()
    assert isinstance(worker.response_queue.get(), ipc.MainProcessTimeout)
