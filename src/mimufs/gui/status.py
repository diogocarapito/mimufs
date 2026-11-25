"""How a status looks: icon + colour + label, never colour alone (CLAUDE.md rule 7)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from mimufs.core.validation.result import Status
from mimufs.gui import strings_pt as S
from mimufs.gui.iconset import icon, pixmap
from mimufs.gui.theme.palette import TOKENS, ThemeName, current_theme


@dataclass(frozen=True)
class Look:
    glyph: str  # icon name
    token: str  # colour token
    label: str  # PT-PT
    state: str  # QSS dynamic property value


LOOKS: dict[Status, Look] = {
    Status.VALID: Look("circle-check", "ok", S.STATUS_VALID, "ok"),
    Status.WARNING: Look("alert-triangle", "warn", S.STATUS_WARNING, "warn"),
    Status.ERROR: Look("circle-x", "err", S.STATUS_ERROR, "err"),
    Status.PENDING: Look("circle", "pend", S.STATUS_PENDING, "pend"),
    Status.SKIPPED: Look("circle-dashed", "pend", S.STATUS_SKIPPED, "pend"),
}
LOCKED = Look("lock", "pend", S.STATUS_LOCKED, "pend")


def theme() -> ThemeName:
    app = QApplication.instance()
    return current_theme(app) if isinstance(app, QApplication) else "dark"


def color(token: str) -> str:
    return TOKENS[theme()][token]


def look(status: Status) -> Look:
    return LOOKS[status]


def status_icon(status: Status, size: int = 16) -> QIcon:
    lk = LOOKS[status]
    return icon(lk.glyph, color(lk.token), size)


def status_pixmap(status: Status, size: int = 16) -> QPixmap:
    lk = LOOKS[status]
    return pixmap(lk.glyph, color(lk.token), size)


def locked_icon(size: int = 16) -> QIcon:
    return icon(LOCKED.glyph, color(LOCKED.token), size)


def severity_label(status: Status) -> str:
    return S.SEVERITY_ERROR if status is Status.ERROR else S.SEVERITY_WARNING
