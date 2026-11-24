"""The M0 GUI shell: window, themes, network badge, update dialog, workers (pytest-qt)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from pytestqt.qtbot import QtBot

from mimufs import update
from mimufs.gui import strings_pt as S
from mimufs.gui.main_window import MainWindow
from mimufs.gui.theme.palette import TOKENS, build_qss, current_theme
from mimufs.gui.update_dialog import UpdateDialog
from mimufs.gui.workers import Worker, WorkerPool
from mimufs.settings import SettingsStore

pytestmark = pytest.mark.gui


@pytest.fixture
def store(tmp_path: Path) -> SettingsStore:
    return SettingsStore(tmp_path / "settings.json")


@pytest.fixture
def window(qtbot: QtBot, store: SettingsStore) -> MainWindow:
    win = MainWindow(store)
    qtbot.addWidget(win)
    win.show()
    return win


def _info(*, supported: bool = True) -> update.UpdateInfo:
    return update.UpdateInfo(
        current="0.0.1",
        latest="0.0.2",
        released="2026-12-01",
        download_url="https://mimufs.com/#download",
        notes_pt=("Leitura mais rápida.",),
        supported=supported,
    )


def test_window_opens_on_the_home_placeholder(window: MainWindow) -> None:
    assert window.windowTitle() == "mimufs"
    assert window.title_bar.app_name.text() == "mimufs"
    assert window.title_bar.project_name.text() == S.NO_PROJECT
    texts = {label.text() for label in window.home.findChildren(QLabel)}
    assert {S.HOME_TITLE, S.PRIVACY_NOTE, S.NO_RECENT_PROJECTS} <= texts
    # Project actions arrive in M1: visible but disabled, with an explanation.
    for button in (window.home.open_button, window.home.new_button):
        assert not button.isEnabled()
        assert button.toolTip() == S.COMING_SOON


def test_theme_toggle_persists_and_restyles(window: MainWindow, store: SettingsStore) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    start = current_theme(app)
    window.toggle_theme()
    other = current_theme(app)
    assert other != start
    assert store.load().theme == other
    assert TOKENS[other]["bg"] in app.styleSheet()
    assert window.title_bar.theme_button.toolTip() == (
        S.THEME_TO_LIGHT if other == "dark" else S.THEME_TO_DARK
    )
    window.toggle_theme()
    assert current_theme(app) == start


def test_saved_theme_is_applied_on_start(qtbot: QtBot, store: SettingsStore) -> None:
    store.update(theme="light")
    win = MainWindow(store)
    qtbot.addWidget(win)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    assert current_theme(app) == "light"


def test_qss_has_no_unfilled_tokens() -> None:
    for theme in TOKENS:
        qss = build_qss(theme)
        assert re.search(r"\{[a-z_0-9]+\}", qss) is None
        assert all(TOKENS[theme][k] in qss for k in ("bg", "panel", "accent", "ok", "warn"))


def test_badge_shows_icon_colour_and_label(window: MainWindow) -> None:
    badge = window.title_bar.net_badge
    # The guard is not installed inside pytest (it's irreversible): the badge says so.
    assert badge.state == "warn"
    assert badge.text.text() == S.NETGUARD_INACTIVE
    assert not badge.icon.pixmap().isNull()


def test_offline_badge_wording() -> None:
    assert S.offline_badge(0) == "offline · 0 ligações de rede"
    assert S.offline_badge(1) == "offline · 1 ligação de rede"


# ------------------------------------------------------------------------------- updates


def test_update_dialog_download_opens_the_browser(qtbot: QtBot, store: SettingsStore) -> None:
    opened: list[QUrl] = []
    dialog = UpdateDialog(_info(), store, open_url=lambda url: opened.append(url) or True)
    qtbot.addWidget(dialog)
    assert dialog.download_button.text() == S.UPDATE_DOWNLOAD
    assert dialog.download_button.isDefault()
    dialog.download_button.click()
    assert [u.toString() for u in opened] == ["https://mimufs.com/#download"]
    assert store.load().ignored_version is None


def test_update_dialog_ignore_remembers_the_version(qtbot: QtBot, store: SettingsStore) -> None:
    dialog = UpdateDialog(_info(), store, open_url=lambda _url: True)
    qtbot.addWidget(dialog)
    dialog.ignore_button.click()
    assert store.load().ignored_version == "0.0.2"


def test_update_dialog_later_changes_nothing(qtbot: QtBot, store: SettingsStore) -> None:
    dialog = UpdateDialog(_info(), store, open_url=lambda _url: True)
    qtbot.addWidget(dialog)
    dialog.later_button.click()
    assert store.load().ignored_version is None


def test_unsupported_version_cannot_be_ignored(qtbot: QtBot, store: SettingsStore) -> None:
    dialog = UpdateDialog(_info(supported=False), store, open_url=lambda _url: True)
    qtbot.addWidget(dialog)
    dialog.show()
    assert not dialog.ignore_button.isVisible()
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert S.UPDATE_UNSUPPORTED in texts
    assert "⚠" in texts  # icon + colour + label


def test_startup_check_shows_the_dialog(
    qtbot: QtBot, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update, "startup_check", lambda _store: _info())
    window.start_update_check()
    qtbot.waitUntil(lambda: window.update_dialog is not None, timeout=5000)
    dialog = window.update_dialog
    assert dialog is not None
    assert dialog.info.latest == "0.0.2"
    buttons = {b.text() for b in dialog.findChildren(QPushButton)}
    assert {S.UPDATE_DOWNLOAD, S.UPDATE_LATER, S.UPDATE_IGNORE} <= buttons


def test_startup_check_respects_the_setting(
    window: MainWindow, store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.update(update_check=False)
    called: list[object] = []
    monkeypatch.setattr(update, "startup_check", lambda s: called.append(s))
    window.start_update_check()
    window.workers.wait(2000)
    assert called == []


# ------------------------------------------------------------------------------- workers


def test_worker_reports_result_and_progress(qtbot: QtBot) -> None:
    pool = WorkerPool()
    progress: list[tuple[int, str]] = []

    def job(x: int, *, progress: object) -> int:
        assert callable(progress)
        progress(50, "metade")
        return x * 2

    worker = Worker(job, 21, with_progress=True)
    worker.signals.progress.connect(lambda p, m: progress.append((p, m)))
    with qtbot.waitSignal(worker.signals.finished, timeout=5000) as blocker:
        pool.start(worker)
    assert blocker.args == [42]
    qtbot.waitUntil(lambda: progress == [(50, "metade")], timeout=2000)
    qtbot.waitUntil(lambda: pool.active == 0, timeout=2000)


def test_worker_reports_failure_without_raising(qtbot: QtBot) -> None:
    def boom() -> None:
        raise ValueError("900000001 must never reach the log")

    worker = Worker(boom)
    with qtbot.waitSignal(worker.signals.failed, timeout=5000) as blocker:
        WorkerPool().start(worker)
    assert isinstance(blocker.args[0], ValueError)
