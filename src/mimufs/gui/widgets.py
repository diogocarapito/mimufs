"""Small reusable widgets: labels, cards, the status pill, the drop zone and the log panel."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mimufs.core.validation.result import Status
from mimufs.gui import strings_pt as S
from mimufs.gui.iconset import icon, pixmap
from mimufs.gui.status import color, look, status_pixmap


def label(
    text: str, role: str | None = None, *, wrap: bool = False, name: str | None = None
) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def card(name: str = "Card") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


def clear(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            break
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            child = item.layout()
            assert child is not None
            clear(child)


def restyle(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class StatusPill(QFrame):
    """``⊗ Erro``: a bordered pill with icon, colour and label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusPill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 12, 3)
        layout.setSpacing(6)
        self.icon = QLabel()
        self.text = QLabel()
        self.text.setObjectName("StatusPillText")
        layout.addWidget(self.icon)
        layout.addWidget(self.text)
        self.status = Status.PENDING

    def set_status(self, status: Status, text: str | None = None) -> None:
        self.status = status
        lk = look(status)
        self.icon.setPixmap(status_pixmap(status, 14))
        self.text.setText(text or lk.label)
        self.setProperty("state", lk.state)
        self.text.setProperty("state", lk.state)
        restyle(self)
        restyle(self.text)


class StatusLine(QWidget):
    """Icon + text, for lists (files, gate table)."""

    def __init__(self, status: Status, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        ic = QLabel()
        ic.setPixmap(status_pixmap(status, 14))
        layout.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(label(text, wrap=True), 1)


class DropZone(QFrame):
    """Accepts dropped files and folders, or picks them with "Importar…"."""

    paths_dropped = Signal(list)  # list[Path]

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(84)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 16, 16)
        layout.setSpacing(16)
        self.icon = QLabel()
        layout.addWidget(self.icon)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = label(title, name="DropTitle")
        self.subtitle = label(subtitle, "muted")
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        layout.addLayout(texts, 1)
        self.button = QPushButton(S.IMPORT_BUTTON)
        self.button.setProperty("variant", "primary")
        self.button.clicked.connect(self._pick)
        layout.addWidget(self.button)
        self._idle = (title, subtitle)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.icon.setPixmap(pixmap("upload", color("text"), 26))

    def set_busy(self, text: str | None) -> None:
        self.button.setEnabled(text is None)
        self.setAcceptDrops(text is None)
        self.title.setText(text or self._idle[0])

    def _pick(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, S.IMPORT_DIALOG, "", S.IMPORT_FILTER)
        if files:
            self.paths_dropped.emit([Path(f) for f in files])

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("hover", True)
            restyle(self)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.setProperty("hover", False)
        restyle(self)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("hover", False)
        restyle(self)
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.paths_dropped.emit(paths)


class LogPanel(QFrame):
    """Collapsible validation log at the bottom ("REGISTO DE VALIDAÇÃO")."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LogPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(4)
        head = QHBoxLayout()
        self.toggle = QToolButton()
        self.toggle.setObjectName("LogToggle")
        self.toggle.setText(S.LOG_TITLE)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.toggled.connect(self._toggled)
        head.addWidget(self.toggle)
        head.addStretch(1)
        self.summary = label("", "mono-muted")
        head.addWidget(self.summary)
        layout.addLayout(head)
        self.text = QPlainTextEdit()
        self.text.setObjectName("LogText")
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(2000)
        self.text.setFixedHeight(110)
        self.text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.text)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        glyph = "chevron-down" if self.toggle.isChecked() else "chevron-right"
        self.toggle.setIcon(icon(glyph, color("muted"), 14))

    def _toggled(self, open_: bool) -> None:
        self.text.setVisible(open_)
        self.refresh_theme()

    def set_events(self, events: Sequence[tuple[datetime, str, str | None, str]]) -> None:
        tokens = {"OK": "ok"}
        lines = []
        for ts, kind, code, message in events:
            tone = tokens.get(kind, "warn" if kind.startswith(("V", "S")) else "text")
            where = f" {code} ·" if code else ""
            lines.append(
                f'<span style="color:{color("muted")}">{ts:%H:%M:%S}</span> '
                f'<span style="color:{color(tone)}">{kind}</span>{where} {_escape(message)}'
            )
        self.text.clear()
        self.text.appendHtml("<br>".join(lines))
        QTimer.singleShot(0, self._scroll_to_end)

    def _scroll_to_end(self) -> None:
        bar = self.text.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_summary(self, text: str) -> None:
        self.summary.setText(text)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class FitScrollArea(QScrollArea):
    """A vertical scroll area whose content takes the viewport width and the height its
    word-wrapped labels need at that width (``widgetResizable`` ignores height-for-width,
    which squashes wrapped text and cards)."""

    def __init__(self, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setWidget(content)

    def refit(self) -> None:
        content = self.widget()
        if content is None:
            return
        layout = content.layout()
        width = self.viewport().width()
        if layout is not None:
            layout.activate()
            width = max(width, layout.totalMinimumSize().width())
            height = (
                layout.totalHeightForWidth(width)
                if layout.hasHeightForWidth()
                else layout.totalSizeHint().height()
            )
            height = max(height, layout.totalMinimumSize().height())
        else:
            height = content.sizeHint().height()
        content.resize(width, max(height, self.viewport().height()))

    def refit_later(self) -> None:
        QTimer.singleShot(0, self.refit)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.refit()
