import logging
from pathlib import Path
import sys

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/sensei_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

class LoggerWriter:
    def __init__(self, level):
        self.level = level

    def write(self, message):
        message = message.strip()
        if message:
            self.level(message)

    def flush(self):
        pass

sys.stdout = LoggerWriter(logging.info)
sys.stderr = LoggerWriter(logging.error)

logger = logging.getLogger(__name__)