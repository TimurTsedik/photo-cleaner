import logging
import os

# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("photo_cleaner")
logger.setLevel(logging.DEBUG)

# File handler for all logs
file_handler = logging.FileHandler(os.path.join(LOG_DIR, "photo_cleaner.log"))
file_handler.setLevel(logging.DEBUG)
file_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
file_handler.setFormatter(file_fmt)

# Stream handler for user‑facing info (INFO and above)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_fmt = logging.Formatter("%(message)s")
stream_handler.setFormatter(stream_fmt)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

def log(msg: str, *, level: str = "info", user: bool = False) -> None:
    """Write *msg* to the logger.
    If *user* is True the message is also printed to STDOUT (preserves current
    admin‑panel behaviour).
    """
    getattr(logger, level.lower(), logger.info)(msg)
    if user:
        print(msg)
