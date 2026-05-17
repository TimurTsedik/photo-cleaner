import logging
import os

# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("photo_cleaner")
logger.setLevel(logging.DEBUG)

# File handler for all logs (no StreamHandler — admin panel uses stdout redirect;
# adding stdout would duplicate messages. User-visible output is handled via
# log(…, user=True) which calls print() directly.)
file_handler = logging.FileHandler(os.path.join(LOG_DIR, "photo_cleaner.log"))
file_handler.setLevel(logging.DEBUG)
file_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
file_handler.setFormatter(file_fmt)

logger.addHandler(file_handler)

def log(msg: str, *, level: str = "info", user: bool = False) -> None:
    """Write *msg* to the logger.
    If *user* is True the message is also printed to STDOUT (preserves current
    admin‑panel behaviour).
    """
    getattr(logger, level.lower(), logger.info)(msg)
    if user:
        print(msg)
