from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGER_NAME = "ptrade_order_tool"


def configure_logging(user_data_dir: Path) -> Path:
    user_data_dir.mkdir(parents=True, exist_ok=True)
    log_path = user_data_dir / "app.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler) and handler.baseFilename != str(log_path):
            logger.removeHandler(handler)
            handler.close()
    if not any(isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(log_path) for handler in logger.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=512_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return log_path


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
