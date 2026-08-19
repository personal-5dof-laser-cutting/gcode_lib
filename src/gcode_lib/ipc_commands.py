from dataclasses import dataclass


class IPCCommand:
    """Base class for all IPC communication commands."""

    pass


@dataclass
class Shutdown(IPCCommand):
    """Request a clean shutdown."""

    pass


@dataclass
class Terminate(IPCCommand):
    """Request process termination."""

    pass


@dataclass
class Heartbeat(IPCCommand):
    """Keepalive message."""

    pass


@dataclass
class QueueMessage(IPCCommand):
    """Send message when space available in remote buffer"""

    message: str


@dataclass
class SendMessage(IPCCommand):
    """Immediately send a message"""

    message: str

@dataclass
class Send(IPCCommand):
    """Auto-select message type"""
    message: str


@dataclass
class SetupReporting(IPCCommand):
    """Request message format and/or auto_reporting"""

    interval_ms: int = 250


@dataclass
class HardwareTimeout(IPCCommand):
    """Indicate a connection loss to the remote hardware."""

    pass


@dataclass
class MainProcessTimeout(IPCCommand):
    """Indicate connection loss to the main process."""

    pass
