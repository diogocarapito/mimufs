"""Tabler SVG icons recoloured with a theme token (see ``icons/README.md``)."""

from __future__ import annotations

from functools import cache
from importlib.resources import files

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

SCALE = 3  # render at 3x so icons stay sharp on HiDPI screens


@cache
def _svg(name: str) -> str:
    return (files("mimufs.gui") / "icons" / f"{name}.svg").read_text(encoding="utf-8")


def pixmap(name: str, color: str, size: int = 18) -> QPixmap:
    data = QByteArray(_svg(name).replace("currentColor", color).encode("utf-8"))
    renderer = QSvgRenderer(data)
    image = QPixmap(QSize(size * SCALE, size * SCALE))
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    image.setDevicePixelRatio(SCALE)
    return image


def icon(name: str, color: str, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))
