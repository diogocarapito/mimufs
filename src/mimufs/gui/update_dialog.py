"""The "new version" dialog (TECH_SPECS §13): Descarregar / Lembrar mais tarde / Ignorar."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from mimufs.gui import strings_pt as S
from mimufs.settings import SettingsStore
from mimufs.update import UpdateInfo


def _open_in_browser(url: QUrl) -> bool:
    # The OS browser downloads the file; mimufs itself never does (no QtNetwork).
    return QDesktopServices.openUrl(url)


class UpdateDialog(QDialog):
    def __init__(
        self,
        info: UpdateInfo,
        store: SettingsStore,
        parent: QWidget | None = None,
        open_url: Callable[[QUrl], bool] = _open_in_browser,
    ) -> None:
        super().__init__(parent)
        self.info = info
        self.store = store
        self._open_url = open_url
        self.setObjectName("UpdateDialog")
        self.setWindowTitle(S.UPDATE_TITLE)
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)

        title = QLabel(S.UPDATE_TITLE)
        title.setProperty("role", "h2")
        layout.addWidget(title)

        body = QLabel(S.UPDATE_BODY.format(latest=info.latest, current=info.current))
        body.setWordWrap(True)
        body.setProperty("role", "body")
        layout.addWidget(body)

        if info.released:
            released = QLabel(S.UPDATE_RELEASED.format(date=info.released))
            released.setProperty("role", "muted")
            layout.addWidget(released)

        if not info.supported:
            warning = QLabel(f"⚠ {S.UPDATE_UNSUPPORTED}")
            warning.setObjectName("UnsupportedWarning")
            warning.setWordWrap(True)
            layout.addWidget(warning)

        if info.notes_pt:
            notes_title = QLabel(S.UPDATE_NOTES.upper())
            notes_title.setProperty("role", "section")
            layout.addSpacing(4)
            layout.addWidget(notes_title)
            notes = QLabel("\n".join(f"•  {line}" for line in info.notes_pt))
            notes.setWordWrap(True)
            layout.addWidget(notes)

        howto = QLabel(S.UPDATE_HOWTO)
        howto.setWordWrap(True)
        howto.setProperty("role", "muted")
        layout.addSpacing(4)
        layout.addWidget(howto)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.ignore_button = QPushButton(S.UPDATE_IGNORE)
        self.ignore_button.clicked.connect(self._ignore)
        self.ignore_button.setVisible(info.supported)  # an unsupported version can't be ignored
        self.later_button = QPushButton(S.UPDATE_LATER)
        self.later_button.clicked.connect(self.reject)
        self.download_button = QPushButton(S.UPDATE_DOWNLOAD)
        self.download_button.setProperty("variant", "primary")
        self.download_button.setDefault(True)
        self.download_button.clicked.connect(self._download)
        buttons.addWidget(self.ignore_button)
        buttons.addStretch(1)
        buttons.addWidget(self.later_button)
        buttons.addWidget(self.download_button)
        layout.addSpacing(8)
        layout.addLayout(buttons)
        self.download_button.setFocus()  # Enter downloads; never ignores by accident

    def _download(self) -> None:
        self._open_url(QUrl(self.info.download_url))
        self.accept()

    def _ignore(self) -> None:
        self.store.update(ignored_version=self.info.latest)
        self.reject()
