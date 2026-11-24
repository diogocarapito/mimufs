"""Application logging. Logs hold events and counts only, never patient data (TECH_SPECS §12.1).

Code must never log patient keys, names or values in the first place; :class:`RedactFilter`
is the safety net. It masks 9-digit numbers (SNS numbers) in every record, on every handler.
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

SNS_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = SNS_RE.sub("<sns>", message)
        if redacted != message:
            record.msg, record.args = redacted, None
        if record.exc_info and record.exc_info[1] is not None:
            # Exception texts can quote cell values: keep the type, drop the message.
            exc = record.exc_info[1]
            record.msg = f"{record.msg} [{type(exc).__name__}]"
            record.exc_info = None
            record.exc_text = None
        return True


def setup_logging(log_dir: Path | None, *, level: int = logging.INFO, console: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handlers: list[logging.Handler] = []
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
        )
    if console:
        handlers.append(logging.StreamHandler(sys.stderr))
    for handler in handlers:
        handler.setFormatter(logging.Formatter(FORMAT))
        handler.addFilter(RedactFilter())
        root.addHandler(handler)
