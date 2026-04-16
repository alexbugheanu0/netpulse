"""
Centralised logging for NetPulse.

All modules call get_logger(__name__) to obtain a named logger that writes
DEBUG+ to the rotating log file. WARNING+ also goes to stderr so operators
see errors in the terminal without losing debug context in the log.
"""

import logging

from app.config import LOG_FILE


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger for the given module name.

    File handler: DEBUG+ → output/logs/netpulse.log
    Stream handler: WARNING+ → stderr (visible in the terminal)
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured — avoid duplicate handlers

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Full debug log to file
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Warnings and errors to stderr so operators don't miss them
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.WARNING)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger
