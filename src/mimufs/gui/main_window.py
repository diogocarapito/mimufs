"""Main window: title bar + the landing page or an open project (TECH_SPECS §14.1, docs/ui/)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mimufs import netguard, update
from mimufs.core.dictionaries import Dictionaries
from mimufs.core.project import Project, ProjectError
from mimufs.gui import strings_pt as S
from mimufs.gui.dictionaries_dialog import DictionaryManager
from mimufs.gui.home import HomePage
from mimufs.gui.iconset import icon, pixmap
from mimufs.gui.new_project import NewProjectDialog
from mimufs.gui.project_view import ProjectView
from mimufs.gui.settings_dialog import SettingsDialog
from mimufs.gui.theme.palette import TOKENS, ThemeName, apply_theme, current_theme, effective_theme
from mimufs.gui.update_dialog import UpdateDialog
from mimufs.gui.workers import Worker, WorkerPool, install_gc_guard
from mimufs.settings import RecentProject, SettingsStore, data_dir

BADGE_REFRESH_MS = 2000


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

        self.app_name = QPushButton(S.APP_NAME)
        self.app_name.setObjectName("AppName")
        self.app_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self.app_name.setFlat(True)
        self.project_name = QLabel(S.NO_PROJECT)
        self.project_name.setObjectName("ProjectName")
        self.net_badge = NetBadge()

        self.theme_button = QToolButton()
        self.theme_button.setObjectName("IconButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip(S.SETTINGS_TITLE)

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


class MainWindow(QMainWindow):
    """Title bar + either the landing page or an open project."""

    def __init__(
        self,
        store: SettingsStore | None = None,
        dictionaries: Dictionaries | None = None,
    ) -> None:
        super().__init__()
        self.store = store or SettingsStore()
        self.dictionaries = dictionaries or Dictionaries(data_dir() / "dicionarios")
        install_gc_guard()  # Qt objects must only be destroyed in the GUI thread
        self.workers = WorkerPool()
        self.update_dialog: UpdateDialog | None = None
        self.project: Project | None = None
        self.view: ProjectView | None = None
        self.setWindowTitle(S.APP_NAME)
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.title_bar = TitleBar()
        self.pages = QStackedWidget()
        self.home = HomePage(self.dictionaries)
        self.pages.addWidget(self.home)
        layout.addWidget(self.title_bar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        self.title_bar.theme_button.clicked.connect(self.toggle_theme)
        self.title_bar.settings_button.clicked.connect(self.open_settings)
        self.title_bar.app_name.clicked.connect(self.go_home)
        self.home.new_requested.connect(self.new_project)
        self.home.open_requested.connect(self.open_project_dialog)
        self.home.recent_requested.connect(lambda path: self.open_path(Path(path)))
        self.home.dictionaries_requested.connect(self.open_dictionaries)
        self.apply_theme(effective_theme(self.store.load().theme))
        self.refresh_home()

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
        self.home.refresh_theme()
        if self.view is not None:
            self.view.refresh_theme()

    def toggle_theme(self) -> None:
        new: ThemeName = "light" if self.theme == "dark" else "dark"
        self.store.update(theme=new)
        self.apply_theme(new)

    # --------------------------------------------------------------------------- projects

    def refresh_home(self) -> None:
        self.home.set_recent(self.store.load().recent_projects)
        self.home.refresh_dictionaries()
        self.home.refresh_theme()

    def go_home(self) -> None:
        self.pages.setCurrentWidget(self.home)
        self.title_bar.project_name.setText(S.NO_PROJECT)
        self.refresh_home()

    def new_project(self) -> Project | None:
        dialog = NewProjectDialog(self.store.load().doctor_name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        info, folder = dialog.result_info, dialog.result_folder
        assert info is not None
        assert folder is not None
        try:
            project = Project.create(folder, info)
        except ProjectError as exc:
            QMessageBox.warning(self, S.CREATE_FAILED, str(exc))
            return None
        if not self.store.load().doctor_name:
            self.store.update(doctor_name=info.doctor)
        self.show_project(project)
        return project

    def open_project_dialog(self) -> None:
        start = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, S.OPEN_PROJECT_TITLE, start, S.OPEN_PROJECT_FILTER
        )
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> Project | None:
        try:
            project = Project.open(path)
        except ProjectError as exc:
            QMessageBox.warning(self, S.OPEN_FAILED, str(exc))
            return None
        self.show_project(project)
        return project

    def show_project(self, project: Project) -> ProjectView:
        if self.view is not None:
            self.pages.removeWidget(self.view)
            self.view.deleteLater()
        if self.project is not None and self.project is not project:
            self.workers.wait(10_000)
            self.project.close()
        self.project = project
        self.view = ProjectView(project, self.workers)
        self.view.progress_changed.connect(self._remember)
        self.pages.addWidget(self.view)
        self.pages.setCurrentWidget(self.view)
        self.title_bar.project_name.setText(project.db_path.name)
        self._remember(self.view.progress)
        return self.view

    def _remember(self, progress: str) -> None:
        if self.project is None:
            return
        info = self.project.info
        self.store.remember_project(
            RecentProject(
                path=str(self.project.db_path),
                name=info.title,
                doctor=info.doctor,
                description=info.description,
                progress=progress,
                last_opened=datetime.now().replace(microsecond=0),
            )
        )

    # ---------------------------------------------------------------------------- dialogs

    def open_settings(self) -> SettingsDialog:
        dialog = SettingsDialog(self.store, self.workers, parent=self)
        dialog.theme_changed.connect(lambda t: self.apply_theme(effective_theme(t)))
        dialog.update_found.connect(self.show_update)
        dialog.open()
        return dialog

    def open_dictionaries(self) -> DictionaryManager:
        dialog = DictionaryManager(self.dictionaries, self)
        dialog.finished.connect(lambda _r: self.home.refresh_dictionaries())
        dialog.open()
        return dialog

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
