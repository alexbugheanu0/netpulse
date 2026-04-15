"""
Centralized logging setup for NetPulse.

All modules call get_logger(__name__) to get a named logger that
writes to both the log file and (at WARNING+ level) the console.
"""

import logging
from app.config import LOG_FILE


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger that writes DEBUG+ to the log file
    and WARNING+ to stderr (Rich handles INFO/DEBUG display).
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
