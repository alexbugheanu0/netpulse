"""Tests for app/logger.py — verifies RotatingFileHandler is used."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from unittest.mock import patch
from pathlib import Path


def test_get_logger_uses_rotating_file_handler(tmp_path):
    """get_logger() must attach a RotatingFileHandler, not a plain FileHandler."""
    log_file = tmp_path / "test_netpulse.log"

    with patch("app.logger.LOG_FILE", log_file):
        # Reset handlers so the test starts fresh regardless of import order.
        logger_name = "test.rotating_check"
        test_logger = logging.getLogger(logger_name)
        test_logger.handlers.clear()

        from app.logger import get_logger
        result = get_logger(logger_name)

    file_handlers = [h for h in result.handlers if isinstance(h, logging.FileHandler)]
    assert file_handlers, "Expected at least one FileHandler"

    rotating = [h for h in file_handlers if isinstance(h, RotatingFileHandler)]
    plain    = [h for h in file_handlers if type(h) is logging.FileHandler]

    assert rotating, "Expected a RotatingFileHandler but found none"
    assert not plain, (
        "Found a plain FileHandler — should have been replaced by RotatingFileHandler"
    )


def test_rotating_file_handler_limits(tmp_path):
    """RotatingFileHandler must cap at 5 MB per file with 5 backups."""
    log_file = tmp_path / "test_netpulse2.log"

    with patch("app.logger.LOG_FILE", log_file):
        logger_name = "test.limits_check"
        logging.getLogger(logger_name).handlers.clear()

        from app.logger import get_logger
        result = get_logger(logger_name)

    rotating = next(
        (h for h in result.handlers if isinstance(h, RotatingFileHandler)), None
    )
    assert rotating is not None

    assert rotating.maxBytes == 5 * 1024 * 1024, (
        f"Expected maxBytes=5242880, got {rotating.maxBytes}"
    )
    assert rotating.backupCount == 5, (
        f"Expected backupCount=5, got {rotating.backupCount}"
    )
