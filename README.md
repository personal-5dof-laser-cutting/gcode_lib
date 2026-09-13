# gcode_lib

`gcode_lib` is a resilient, high-performance Python library for streaming GCode to machine controller units (MCUs) like the FluidNC Corgi. It is designed to handle complex, multi-axis motion programs by continuously feeding the hardware planner, ensuring smooth kinematics while providing strict safety fallbacks.

## Key Features

* **High-Performance Streaming:** Uses a simulated buffer and character-counting protocol rather than basic ping-pong communication. This keeps the MCU's planner full, enabling dynamic acceleration and smooth movements without stalling the machine.
* **Fail-Safe Process Isolation:** Communication runs in a dedicated `CommunicationWorker` process. If your main application crashes or network latency spikes (e.g., over WebSockets/Telnet), the worker remains active to safely issue an emergency stop (E-STOP) and prevent hardware damage.
* **Real-Time Command Priority:** Out-of-band instructions like feedholds (`!`) and status reports (`?`) bypass the standard transmission queue to execute with zero latency.
* **Fault Transparency:** Includes extensive, multi-layer logging for debugging hardware faults, loose cables, and network drops.
* **Hardware & Interface Agnostic:** Extendable `Driver` architecture supports Serial, WebSockets, and Telnet connections across different MCU firmwares.

## Architecture

The library is split into three core components to ensure type safety, responsiveness, and safe degradation:

1. **`CommunicationProxy`:** The user-facing abstraction layer. It exposes simple methods like `open`, `close`, `send`, and `read_message` (with optional non-blocking timeouts) to interact with the machine.
2. **`CommunicationWorker`:** An independent, continuous background process. It handles RX/TX queue management, tracks the remote buffer state using ACK messages, and runs the hardware and process watchdogs to monitor system health.
3. **`Driver`:** A stateless layer defining the specific interface (e.g., USB serial vs. Wi-Fi) and the hardware protocol (classifying ACKs, querying buffer sizes).

## Quick Start

The following example demonstrates how to initialize a serial connection to a FluidNC controller, send a real-time status query, and read the response.

```python
from gcode_lib import CommunicationProxy, FluidNCSerialDriver
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(filename)-25s %(levelname)-8s %(message)s",
)

log = logging.getLogger(__name__)

if __name__ == "__main__":
    # 1. Initialize the driver for your specific hardware and interface
    driver = FluidNCSerialDriver("/dev/ttyUSB0")

    # 2. Connect the proxy (automatically spawns the CommunicationWorker)
    with CommunicationProxy(driver=driver).connect(setup_reporting=False) as proxy:
        
        # 3. Send an out-of-band status request
        proxy.send("?")
        
        # 4. Read the machine's response (with a 1-second timeout)
        print(proxy.read_message(timeout=1))

```

## Tests

Tests are written with pytest `python -m pytest` or `uv run pytest`.
