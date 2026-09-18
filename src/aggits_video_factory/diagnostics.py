from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import application_data_root


LOG_FILENAME = "crispy-bits-desktop.log"
MAX_LOG_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3
_LOGGER_NAME = "crispy_bits"


class SecretRedactionFilter(logging.Filter):
    _patterns = (
        re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s,;]+)"),
        re.compile(r"(?i)((?:api[_ -]?key|secret|signature|token)\s*[:=]\s*)([^\s,;]+)"),
        re.compile(r"(?i)(x-crispy-signature\s*[:=]\s*)([^\s,;]+)"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub(r"\1[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def log_directory(root: Path | None = None) -> Path:
    return (root or application_data_root()) / "logs"


def configure_logging(root: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    directory = log_directory(root)
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / LOG_FILENAME).resolve()
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename).resolve() == target:
            return logger
    handler = RotatingFileHandler(
        target,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(SecretRedactionFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return configure_logging()


def close_logging(root: Path | None = None) -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    target = (log_directory(root) / LOG_FILENAME).resolve() if root else None
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler) and (target is None or Path(handler.baseFilename).resolve() == target):
            handler.close()
            logger.removeHandler(handler)


def open_log_folder(root: Path | None = None) -> None:
    directory = log_directory(root)
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(directory)  # type: ignore[attr-defined]
        return
    raise OSError(f"Open the log folder manually: {directory}")
