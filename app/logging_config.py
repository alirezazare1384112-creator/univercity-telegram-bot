"""Central logging setup: console + rotating file handler.

Sensitive values (bot token, database password) are never logged.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import Settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(settings: Settings) -> None:
    """Configure root logging once, safe to call multiple times."""
    root = logging.getLogger()
    if getattr(root, "_student_assistant_configured", False):
        return

    level = getattr(logging, settings.log_level, logging.INFO)
    root.setLevel(level)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        settings.log_dir / "bot.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Third party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    root._student_assistant_configured = True  # type: ignore[attr-defined]
    logging.info("Logging initialised (level=%s)", settings.log_level)
