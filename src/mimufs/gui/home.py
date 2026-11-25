"""Landing page "Projetos" (PRD §6.2): recent projects, new/open, dictionaries, privacy note."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mimufs import __version__
from mimufs.core.dictionaries import Dictionaries
from mimufs.gui import strings_pt as S
from mimufs.gui.iconset import pixmap
from mimufs.gui.status import color
from mimufs.gui.widgets import card, clear, label
from mimufs.settings import RecentProject


def relative_time(when: datetime | None, now: datetime | None = None) -> str:
    """ "há 2 dias", "hoje"… for the recent-projects list."""
    if when is None:
        return ""
    now = now or datetime.now()
    days = (now.date() - when.date()).days
    if days <= 0:
        return "hoje"
    if days == 1:
        return "ontem"
    if days < 7:
        return f"há {days} dias"
    if days < 30:
        weeks = days // 7
        return f"há {weeks} semana{'s' if weeks > 1 else ''}"
    months = days // 30
    return f"há {months} {'mês' if months == 1 else 'meses'}"


def short_path(path: Path) -> str:
    home = Path.home()
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


class RecentCard(QFrame):
    clicked = Signal(str)

    def __init__(self, entry: RecentProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("RecentCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        exists = Path(entry.path).is_file()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        self.icon = QLabel()
        self.icon.setPixmap(pixmap("folder", color("accent_text"), 22))
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(entry.name or Path(entry.path).stem, name="RecentTitle"))
        subtitle = " · ".join(x for x in (entry.doctor, entry.description) if x)
        if subtitle:
            texts.addWidget(label(subtitle, "muted"))
        texts.addWidget(label(short_path(Path(entry.path).parent), "mono-muted"))
        layout.addLayout(texts, 1)
        side = QVBoxLayout()
        side.setSpacing(2)
        side.addWidget(label(entry.progress if exists else S.RECENT_MISSING, "small"), 0,
                       Qt.AlignmentFlag.AlignRight)  # fmt: skip
        when = relative_time(entry.last_opened)
        if when:
            side.addWidget(label(S.RECENT_OPENED.format(when=when), "mono-muted"), 0,
                           Qt.AlignmentFlag.AlignRight)  # fmt: skip
        side.addStretch(1)
        layout.addLayout(side)
        self.setEnabled(exists)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.entry.path)


class HomePage(QWidget):
    new_requested = Signal()
    open_requested = Signal()
    recent_requested = Signal(str)
    dictionaries_requested = Signal()

    def __init__(self, dictionaries: Dictionaries, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.dictionaries = dictionaries
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)
        page = QWidget()
        scroll.setWidget(page)
        outer = QHBoxLayout(page)
        outer.setContentsMargins(24, 48, 24, 24)
        outer.addStretch(1)

        column = QWidget()
        column.setMaximumWidth(980)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        body = QVBoxLayout(column)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(6)
        titles.addWidget(label(S.HOME_KICKER.format(version=__version__).upper(), "kicker"))
        titles.addWidget(label(S.HOME_TITLE, "h1"))
        titles.addWidget(label(S.HOME_SUBTITLE, "muted", wrap=True))
        header.addLayout(titles, 1)
        self.open_button = QPushButton(S.OPEN_PROJECT)
        self.open_button.clicked.connect(self.open_requested)
        self.new_button = QPushButton(S.NEW_PROJECT)
        self.new_button.setProperty("variant", "primary")
        self.new_button.clicked.connect(self.new_requested)
        for button in (self.open_button, self.new_button):
            header.addWidget(button, 0, Qt.AlignmentFlag.AlignBottom)
        body.addLayout(header)
        body.addSpacing(22)

        columns = QHBoxLayout()
        columns.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(label(S.RECENT_PROJECTS, "section"))
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(10)
        left.addLayout(self.recent_box)
        left.addStretch(1)
        columns.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(16)
        self.dict_card, self.dict_layout = card()
        right.addWidget(self.dict_card)
        self.privacy_card = QFrame()
        self.privacy_card.setObjectName("Card")
        privacy = QHBoxLayout(self.privacy_card)
        privacy.setContentsMargins(16, 16, 16, 16)
        privacy.setSpacing(10)
        self.privacy_icon = QLabel()
        self.privacy_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        privacy.addWidget(self.privacy_icon)
        privacy.addWidget(label(S.PRIVACY_NOTE, "body", wrap=True), 1)
        right.addWidget(self.privacy_card)
        right.addStretch(1)
        columns.addLayout(right, 1)
        body.addLayout(columns, 1)

        outer.addWidget(column, 6)
        outer.addStretch(1)
        self.recent_cards: list[RecentCard] = []

    def set_recent(self, entries: list[RecentProject]) -> None:
        clear(self.recent_box)
        self.recent_cards = []
        if not entries:
            empty, layout = card()
            layout.addWidget(label(S.NO_RECENT_PROJECTS, "muted", wrap=True))
            self.recent_box.addWidget(empty)
            return
        for entry in entries:
            widget = RecentCard(entry)
            widget.clicked.connect(self.recent_requested)
            self.recent_cards.append(widget)
            self.recent_box.addWidget(widget)

    def refresh_dictionaries(self) -> None:
        clear(self.dict_layout)
        self.dict_layout.addWidget(label(S.DICTIONARIES, "section"))
        for info in self.dictionaries.info():
            row = QHBoxLayout()
            row.addWidget(label(S.DICT_TITLES[info.key], "body"))
            row.addStretch(1)
            detail = f"{info.rows} {S.DICT_UNITS[info.key]}"
            if info.user_editable:
                detail += f" · {S.DICT_EDITED if info.edited else S.DICT_EDITABLE}"
            row.addWidget(label(detail, "mono-muted"))
            self.dict_layout.addLayout(row)
        button = QPushButton(S.MANAGE_DICTIONARIES)
        button.clicked.connect(self.dictionaries_requested)
        row = QHBoxLayout()
        row.addWidget(button)
        row.addStretch(1)
        self.dict_layout.addLayout(row)

    def refresh_theme(self) -> None:
        self.privacy_icon.setPixmap(pixmap("shield-check", color("ok"), 18))
        for widget in self.recent_cards:
            widget.icon.setPixmap(pixmap("folder", color("accent_text"), 22))
