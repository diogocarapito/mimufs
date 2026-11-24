"""QApplication set-up and the GUI entry point."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from importlib.resources import as_file, files
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from mimufs import __version__
from mimufs.gui import strings_pt as S
from mimufs.gui.main_window import MainWindow
from mimufs.gui.theme.palette import effective_theme
from mimufs.settings import SettingsStore

log = logging.getLogger(__name__)
FONT_SUFFIXES = (".ttf", ".otf")


def load_bundled_fonts() -> int:
    """Register the fonts shipped in ``mimufs/gui/fonts`` (Inter, JetBrains Mono; OFL).

    Never fetched from the network. Missing fonts fall back to system fonts.
    """
    loaded = 0
    with as_file(files("mimufs.gui")) as package_dir:
        folder = Path(package_dir) / "fonts"
        if not folder.is_dir():
            return 0
        for path in sorted(folder.iterdir()):
            if (
                path.suffix.lower() in FONT_SUFFIXES
                and QFontDatabase.addApplicationFont(str(path)) >= 0
            ):
                loaded += 1
    return loaded


def app_icon() -> QIcon:
    with as_file(files("mimufs.gui") / "icons" / "app.png") as path:
        return QIcon(str(path)) if Path(path).is_file() else QIcon()


def create_application(argv: Sequence[str]) -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(list(argv))
    app.setApplicationName(S.APP_NAME)
    app.setApplicationDisplayName(S.APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("com.mimufs.mimufs")
    app.setWindowIcon(app_icon())
    load_bundled_fonts()
    return app


def run(argv: Sequence[str], store: SettingsStore | None = None) -> int:
    app = create_application(argv)
    store = store or SettingsStore()
    window = MainWindow(store)
    hints = QGuiApplication.styleHints()

    def follow_system() -> None:
        if store.load().theme == "system":
            window.apply_theme(effective_theme("system"))

    hints.colorSchemeChanged.connect(follow_system)
    window.show()
    window.start_update_check()
    log.info("mimufs %s started (Qt %s)", __version__, app.platformName())
    code = app.exec()
    window.workers.wait(6000)
    return code
