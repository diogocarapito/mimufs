"""Settings (PRD §7.3): doctor name, theme, update check (+ "Verificar agora"), About."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mimufs import __version__, update
from mimufs.gui import strings_pt as S
from mimufs.gui.widgets import label
from mimufs.gui.workers import Worker, WorkerPool
from mimufs.settings import SettingsStore

THEMES = (("system", S.THEME_SYSTEM), ("dark", S.THEME_DARK), ("light", S.THEME_LIGHT))


def explicit_check() -> update.UpdateInfo | None:
    """None = up to date; raises when the check itself fails (offline, bad reply)."""
    doc = update.fetch_version_doc()
    return update.evaluate(doc, __version__, None)


class SettingsDialog(QDialog):
    theme_changed = Signal(str)
    update_found = Signal(object)  # update.UpdateInfo

    def __init__(self, store: SettingsStore, workers: WorkerPool | None = None,
                 check: Callable[[], update.UpdateInfo | None] = explicit_check,
                 parent: QWidget | None = None) -> None:  # fmt: skip
        super().__init__(parent)
        self.store = store
        self.workers = workers or WorkerPool()
        self._check = check
        settings = store.load()
        self.setWindowTitle(S.SETTINGS_TITLE)
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(6)
        lay.addWidget(label(S.SETTINGS_TITLE, "h2"))

        lay.addSpacing(8)
        lay.addWidget(label(S.SETTINGS_DOCTOR, "h3"))
        self.doctor = QLineEdit(settings.doctor_name)
        lay.addWidget(self.doctor)
        lay.addWidget(label(S.SETTINGS_DOCTOR_HELP, "small"))

        lay.addSpacing(8)
        lay.addWidget(label(S.SETTINGS_THEME, "h3"))
        self.theme = QComboBox()
        for value, text in THEMES:
            self.theme.addItem(text, value)
        self.theme.setCurrentIndex([v for v, _ in THEMES].index(settings.theme))
        lay.addWidget(self.theme)

        lay.addSpacing(8)
        self.updates = QCheckBox(S.SETTINGS_UPDATES)
        self.updates.setChecked(settings.update_check)
        lay.addWidget(self.updates)
        row = QHBoxLayout()
        self.check_now = QPushButton(S.CHECK_NOW)
        self.check_now.clicked.connect(self._check_now)
        self.check_result = label("", "small")
        row.addWidget(self.check_now)
        row.addWidget(self.check_result, 1)
        lay.addLayout(row)

        lay.addSpacing(10)
        lay.addWidget(label(S.ABOUT, "h3"))
        lay.addWidget(label(S.ABOUT_TEXT.format(version=__version__), "small", wrap=True))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(S.CANCEL)
        cancel.clicked.connect(self.reject)
        save = QPushButton(S.SAVE)
        save.setProperty("variant", "primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        lay.addSpacing(10)
        lay.addLayout(buttons)

    def _save(self) -> None:
        theme = str(self.theme.currentData())
        before = self.store.load().theme
        self.store.update(
            doctor_name=self.doctor.text().strip(),
            theme=theme,
            update_check=self.updates.isChecked(),
        )
        if theme != before:
            self.theme_changed.emit(theme)
        self.accept()

    def _check_now(self) -> None:
        """ "Verificar agora": an explicit check, even when automatic checks are off."""
        self.check_now.setEnabled(False)
        self.check_result.setText(S.UPDATE_CHECKING)
        worker = Worker(self._check)
        self.workers.start(worker, on_finished=self._checked, on_failed=self._check_failed)

    def _checked(self, info: object) -> None:
        self.check_now.setEnabled(True)
        if isinstance(info, update.UpdateInfo):
            self.check_result.setText("")
            self.update_found.emit(info)
        else:
            self.check_result.setText(S.UPDATE_NONE)

    def _check_failed(self, _exc: BaseException) -> None:
        self.check_now.setEnabled(True)
        self.check_result.setText(S.UPDATE_FAILED)
