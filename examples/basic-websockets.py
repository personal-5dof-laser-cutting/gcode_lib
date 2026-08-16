import logging
from gcode_lib import CommunicationProxy, FluidNCWebsocketsDriver

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(filename)-25s %(levelname)-8s %(message)s",
)

log = logging.getLogger(__name__)

if __name__ == "__main__":
    # Replace with your FluidNC controller's IP address or hostname.
    # Port 81 is the default for FluidNC WebSockets.
    driver = FluidNCWebsocketsDriver(address="192.168.1.100", port=81)

    with CommunicationProxy(driver=driver).connect(setup_reporting=False) as proxy:
        proxy.send("?")
        print(proxy.read_message(timeout=1))
