from gcode_lib import CommunicationProxy, FluidNCSerialDriver
import time
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(filename)-25s %(levelname)-8s %(message)s",
)

log = logging.getLogger(__name__)

if __name__ == "__main__":
    driver = FluidNCSerialDriver("/dev/ttyUSB0")
    proxy = CommunicationProxy(driver=driver)

    log.info("Connecting")
    proxy.connect(setup_reporting=False)
    time.sleep(5)
    log.info("Sending Message")
    proxy.send_message("?")
    time.sleep(5)
    log.info("Reading Message")
    print(proxy.read_message())
    log.info("Closing")
    proxy.close()
