import logging

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("banker")
logging.getLogger("apscheduler.scheduler").setLevel(logging.INFO)
logging.getLogger("apscheduler.executors.default").setLevel(logging.ERROR)
