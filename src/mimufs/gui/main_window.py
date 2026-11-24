"""Main window, M0 shell: title bar + home placeholder (TECH_SPECS §14.1, docs/ui/).

M1 replaces the placeholder with the real ``HomePage`` (recent projects, new-project dialog,
dictionaries card) and adds the project layout (PhaseNav, content, validation pane, log).
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mimufs import __version__, netguard, update
from mimufs.gui import strings_pt as S
from mimufs.gui.iconset import icon, pixmap
from mimufs.gui.theme.palette import TOKENS, ThemeName, apply_theme, current_theme, effective_theme
from mimufs.gui.update_dialog import UpdateDialog
from mimufs.gui.workers import Worker, WorkerPool
from mimufs.settings import SettingsStore

BADGE_REFRESH_MS = 2000


def _label(text: str, role: str | None = None, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    label.setWordWrap(wrap)
    return label


class NetBadge(QWidget):
    """``✓ offline · 0 ligações de rede``: icon + colour + label, never colour alone."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.icon = QLabel()
        self.text = QLabel()
        self.text.setObjectName("NetBadge")
        layout.addWidget(self.icon)
        layout.addWidget(self.text)
        self.theme: ThemeName = "dark"
        self.refresh()

    @property
    def state(self) -> str:
        return cast(str, self.text.property("state"))

    def refresh(self) -> None:
        stats = netguard.stats()
        if stats.installed:
            state, glyph, text = "ok", "shield-check", S.offline_badge(stats.allowed)
            tooltip = S.NETGUARD_ACTIVE_TOOLTIP.format(blocked=stats.blocked)
        else:
            state, glyph, text = "warn", "alert-triangle", S.NETGUARD_INACTIVE
            tooltip = S.NETGUARD_INACTIVE_TOOLTIP
        if self.text.text() != text or self.text.property("state") != state:
            self.text.setText(text)
            self.text.setProperty("state", state)
            self.text.style().unpolish(self.text)
            self.text.style().polish(self.text)
        self.icon.setPixmap(pixmap(glyph, TOKENS[self.theme][state], 16))
        self.setToolTip(tooltip)


class TitleBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(14)

        self.app_name = QLabel(S.APP_NAME)
        self.app_name.setObjectName("AppName")
        self.project_name = QLabel(S.NO_PROJECT)
        self.project_name.setObjectName("ProjectName")
        self.net_badge = NetBadge()

        self.theme_button = QToolButton()
        self.theme_button.setObjectName("IconButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setEnabled(False)  # Settings dialog arrives in M1
        self.settings_button.setToolTip(S.SETTINGS_SOON)

        layout.addWidget(self.app_name)
        layout.addWidget(self.project_name)
        layout.addStretch(1)
        layout.addWidget(self.net_badge)
        layout.addSpacing(4)
        layout.addWidget(self.theme_button)
        layout.addWidget(self.settings_button)

    def apply_theme(self, theme: ThemeName) -> None:
        t = TOKENS[theme]
        self.net_badge.theme = theme
        self.net_badge.refresh()
        self.theme_button.setIcon(icon("brightness", t["text"]))
        self.theme_button.setToolTip(S.THEME_TO_LIGHT if theme == "dark" else S.THEME_TO_DARK)
        self.settings_button.setIcon(icon("settings", t["muted"]))


class HomePlaceholder(QWidget):
    """The landing page's frame; projects, dialogs and dictionaries come in M1."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QHBoxLayout(self)
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
        titles.addWidget(_label(S.HOME_KICKER.format(version=__version__), "kicker"))
        titles.addWidget(_label(S.HOME_TITLE, "h1"))
        titles.addWidget(_label(S.HOME_SUBTITLE, "muted", wrap=True))
        header.addLayout(titles, 1)
        self.open_button = QPushButton(S.OPEN_PROJECT)
        self.new_button = QPushButton(S.NEW_PROJECT)
        self.new_button.setProperty("variant", "primary")
        for button in (self.open_button, self.new_button):
            button.setEnabled(False)
            button.setToolTip(S.COMING_SOON)
            header.addWidget(button, 0, Qt.AlignmentFlag.AlignBottom)
        body.addLayout(header)
        body.addSpacing(22)

        columns = QHBoxLayout()
        columns.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(_label(S.RECENT_PROJECTS, "section"))
        empty = QFrame()
        empty.setObjectName("Card")
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(18, 18, 18, 18)
        self.empty_label = _label(S.NO_RECENT_PROJECTS, "muted", wrap=True)
        empty_layout.addWidget(self.empty_label)
        left.addWidget(empty)
        left.addStretch(1)
        columns.addLayout(left, 2)

        right = QVBoxLayout()
        self.privacy_card = QFrame()
        self.privacy_card.setObjectName("Card")
        privacy = QHBoxLayout(self.privacy_card)
        privacy.setContentsMargins(16, 16, 16, 16)
        privacy.setSpacing(10)
        self.privacy_icon = QLabel()
        self.privacy_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        privacy.addWidget(self.privacy_icon)
        privacy.addWidget(_label(S.PRIVACY_NOTE, "body", wrap=True), 1)
        right.addWidget(self.privacy_card)
        right.addStretch(1)
        columns.addLayout(right, 1)
        body.addLayout(columns, 1)

        outer.addWidget(column, 6)
        outer.addStretch(1)

    def apply_theme(self, theme: ThemeName) -> None:
        self.privacy_icon.setPixmap(pixmap("shield-check", TOKENS[theme]["ok"], 18))


class MainWindow(QMainWindow):
    def __init__(self, store: SettingsStore | None = None) -> None:
        super().__init__()
        self.store = store or SettingsStore()
        self.workers = WorkerPool()
        self.update_dialog: UpdateDialog | None = None
        self.setWindowTitle(S.APP_NAME)
        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.title_bar = TitleBar()
        self.home = HomePlaceholder()
        layout.addWidget(self.title_bar)
        layout.addWidget(self.home, 1)
        self.setCentralWidget(central)

        self.title_bar.theme_button.clicked.connect(self.toggle_theme)
        self.apply_theme(effective_theme(self.store.load().theme))

        self._badge_timer = QTimer(self)
        self._badge_timer.timeout.connect(self.title_bar.net_badge.refresh)
        self._badge_timer.start(BADGE_REFRESH_MS)

    # ------------------------------------------------------------------------------ theme

    @property
    def theme(self) -> ThemeName:
        app = QApplication.instance()
        return current_theme(cast(QApplication, app))

    def apply_theme(self, theme: ThemeName) -> None:
        app = cast(QApplication, QApplication.instance())
        apply_theme(app, theme)
        self.title_bar.apply_theme(theme)
        self.home.apply_theme(theme)

    def toggle_theme(self) -> None:
        new: ThemeName = "light" if self.theme == "dark" else "dark"
        self.store.update(theme=new)
        self.apply_theme(new)

    # ----------------------------------------------------------------------------- update

    def start_update_check(self) -> None:
        """The automatic start-up check (at most every 24 h, only if enabled)."""
        if not update.is_due(self.store.load()):
            return
        self.workers.start(
            Worker(update.startup_check, self.store), on_finished=self._on_update_result
        )

    def _on_update_result(self, info: object) -> None:
        self.title_bar.net_badge.refresh()
        if isinstance(info, update.UpdateInfo):
            self.show_update(info)

    def show_update(self, info: update.UpdateInfo) -> UpdateDialog:
        self.update_dialog = UpdateDialog(info, self.store, self)
        self.update_dialog.open()
        return self.update_dialog
