from gcode_lib import CommunicationProxy, FluidNCSerialDriver
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(filename)-25s %(levelname)-8s %(message)s",
)

log = logging.getLogger(__name__)

if __name__ == "__main__":
    driver = FluidNCSerialDriver("/dev/ttyUSB0")

    with CommunicationProxy(driver=driver).connect(setup_reporting=False) as proxy:
        proxy.send("?")
        print(proxy.read_message(timeout=1))
