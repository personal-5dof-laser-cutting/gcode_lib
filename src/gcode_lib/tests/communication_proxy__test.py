import pytest
import queue
import time
from unittest.mock import MagicMock

from gcode_lib.communication_worker import CommunicationWorker


@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.safety_shutoff_command = "\x18"
    driver.read_message.return_value = None
    return driver


@pytest.fixture
def worker(mock_driver):
    # Using thread-safe standard queues avoids OS-level multiprocessing locks in tests
    w = CommunicationWorker(driver=mock_driver, timeout_sec=0.1, buffer_size=128)
    w.cmd_queue = queue.Queue()
    w.response_queue = queue.Queue()
    return w


def test_successful_connect_and_shutdown(worker, mock_driver):
    worker.cmd_queue.put("SHUTDOWN")
    worker.run()

    assert worker.ready_event.is_set()
    mock_driver.connect.assert_called_once()
    mock_driver.close.assert_called_once()


def test_buffer_management(worker, mock_driver):
    # Enqueue a message
    worker.cmd_queue.put(("QUEUE", "G0 X10"))
    worker.cmd_queue.put("SHUTDOWN")  # ensures the loop exits

    worker.run()

    # 6 chars + 1 newline = 7 bytes
    mock_driver.send.assert_called_with("G0 X10")
    assert worker.bytes_in_buffer == 7
    assert len(worker._pending_line_lengths) == 1


def test_ack_frees_buffer(worker, mock_driver):
    worker._pending_line_lengths.append(10)  # Pretend we have 10 bytes in transit

    # Provide enough responses for the reads before the shutdown
    mock_driver.read_message.side_effect = ["ok", None, None]

    # Iteration 1: Worker consumes HEARTBEAT, moves on to read_message()
    worker.cmd_queue.put("HEARTBEAT")

    # Iteration 2: Worker consumes SHUTDOWN, cleanly breaks the outer loop
    worker.cmd_queue.put("SHUTDOWN")

    worker.run()

    assert worker.bytes_in_buffer == 0
    assert worker.response_queue.get() == "ok"


def test_hardware_disconnect_handling(worker, mock_driver):
    mock_driver.read_message.side_effect = Exception("Unplugged")

    worker.run()  # Loop should break automatically

    assert (
        worker._running.is_set() is True
    )  # It broke the loop, didn't unset running cleanly yet
    assert worker.response_queue.get() == "SYS:HARDWARE_DISCONNECTED"


def test_watchdog_triggers_estop(worker, mock_driver):
    # Send a heartbeat to arm it
    worker.cmd_queue.put("HEARTBEAT")

    # Monkeypatch time.monotonic to instantly trigger the timeout
    original_monotonic = time.monotonic

    def time_travel():
        return original_monotonic() + 1.0  # Jump 1 second forward

    with pytest.MonkeyPatch.context() as m:
        # After arming the watchdog, we manipulate time inside the loop
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

    # Safety shutoff must be fired
    mock_driver.send_message.assert_called_with("\x18", append_newline=False)
    mock_driver.terminate.assert_called_once()
    assert worker.response_queue.get() == "SYS:WATCHDOG_TIMEOUT"
