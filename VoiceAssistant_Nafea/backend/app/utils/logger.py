import logging
import time
import sys
from contextlib import contextmanager

from app.config import settings

# Set up logging format
handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
if settings.LOG_FILE:
    handlers.append(logging.FileHandler(settings.LOG_FILE, encoding="utf-8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=handlers,
)

logger = logging.getLogger("voice-ai-agent")

@contextmanager
def log_duration(activity_name: str):
    """Context manager to log the duration of a block of code."""
    start_time = time.perf_counter()
    logger.info(f"Starting activity: {activity_name}")
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        logger.info(f"Finished activity: {activity_name} | Duration: {duration:.3f}s")
