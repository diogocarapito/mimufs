"""M1 "Done when": deliberately broken fixtures produce the right 🟢/🟠/🔴 and messages in the UI.

Every scenario of ``tests/fixtures/broken.py`` is imported through the project view (worker
thread included); the status pill, slot tiles and issue cards must match the expectations.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QPushButton
from pytestqt.qtbot import QtBot

from mimufs.core.dictionaries import Dictionaries
from mimufs.core.project import Project, ProjectInfo
from mimufs.core.validation.result import Status
from mimufs.gui import strings_pt as S
from mimufs.gui.dictionaries_dialog import DictionaryManager
from mimufs.gui.home import RecentCard
from mimufs.gui.main_window import MainWindow
from mimufs.gui.new_project import NewProjectDialog
from mimufs.gui.panes import IssueCard
from mimufs.gui.project_view import ProjectView
from mimufs.gui.report_page import SlotTile
from mimufs.gui.settings_dialog import SettingsDialog
from mimufs.gui.status import look, severity_label
from mimufs.settings import SettingsStore
from tests.fixtures import make_fixtures as mf
from tests.fixtures.broken import Scenario

pytestmark = pytest.mark.gui
INFO = ProjectInfo(unit=mf.UNIT, doctor=mf.PROJECT_DOCTOR, years=(mf.YEAR,), description="Teste")


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> MainWindow:
    store = SettingsStore(tmp_path / "settings.json")
    win = MainWindow(store, Dictionaries(tmp_path / "dicionarios"))
    qtbot.addWidget(win)
    win.show()
    return win


def open_project(window: MainWindow, folder: Path) -> ProjectView:
    return window.show_project(Project.create(folder, INFO))


def import_and_wait(qtbot: QtBot, view: ProjectView, paths: list[Path], code: str = "") -> None:
    view.import_paths(paths, code)
    qtbot.waitUntil(lambda: not view.busy, timeout=60_000)


def pane_texts(view: ProjectView, name: str) -> list[str]:
    return [w.text() for w in view.pane.findChildren(QLabel) if w.objectName() == name]


def tile_states(view: ProjectView) -> list[str]:
    return [str(t.property("state")) for t in view.report_page.findChildren(SlotTile)]


# ------------------------------------------------------------------- the M1 criterion


def test_broken_fixtures_show_the_right_status_and_messages(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, broken_scenarios: dict[str, Scenario]
) -> None:
    failures: dict[str, str] = {}
    for name, sc in broken_scenarios.items():
        if sc.code is None:
            continue
        view = open_project(window, tmp_path / name)
        import_and_wait(qtbot, view, list(sc.files), sc.code)
        view.select(("report", sc.code))
        expected = max((s for _, s in sc.expect), default=Status.VALID)
        problems = []
        if view.pill.text.text() != look(expected).label:
            problems.append(f"pill {view.pill.text.text()!r}")
        where = " | ".join(pane_texts(view, "IssueWhere"))
        for check_id, severity in sc.expect:
            if f"{severity_label(severity)} {check_id}" not in where:
                problems.append(f"no card for {check_id}")
        messages = " | ".join(pane_texts(view, "IssueMessage"))
        problems += [f"missing text {t!r}" for t in sc.contains if t not in messages]
        if len(view.pane.findChildren(IssueCard)) < len(sc.expect):
            problems.append("too few issue cards")
        states = tile_states(view)
        if any(cid.startswith("V") and sev is Status.ERROR for cid, sev in sc.expect) and (
            "err" not in states and not any(cid in ("V04", "V06") for cid, _ in sc.expect)
        ):
            problems.append(f"no red tile in {states}")
        if problems:
            failures[name] = "; ".join(problems)
    assert failures == {}


def test_refused_files_are_explained(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, broken_scenarios: dict[str, Scenario]
) -> None:
    view = open_project(window, tmp_path / "p")
    paths = [broken_scenarios[n].files[0] for n in ("V01_html", "V01_corrupt", "V02_unknown")]
    import_and_wait(qtbot, view, paths, "P01.01.L01")
    view.select(("report", "P01.01.L01"))
    assert S.LAST_IMPORT in [w.text() for w in view.pane.findChildren(QLabel)]
    messages = " | ".join(pane_texts(view, "IssueMessage"))
    assert "não é um Excel verdadeiro" in messages
    assert "danificado" in messages
    assert "Relatório não reconhecido" in messages
    assert view.project.files() == []


def test_wrong_report_drop(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    view = open_project(window, tmp_path / "p")
    import_and_wait(
        qtbot, view, [synthetic_fixtures["valid/P01.01.L03/2024-12"].path], "P01.01.L01"
    )
    view.select(("report", "P01.01.L01"))
    messages = " | ".join(pane_texts(view, "IssueMessage"))
    assert "Este ficheiro é o P01.01.L03" in messages
    assert "não o P01.01.L01" in messages


# ------------------------------------------------------------------------- workflow


def test_gate_unlocks_after_a_complete_import(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    view = open_project(window, tmp_path / "p")
    view.select(("gate",))
    assert not view.next.isEnabled()
    assert view.pill.text.text() == S.STATUS_WARNING
    valid = [f.path for f in synthetic_fixtures.values() if f.kind == "valid"]
    import_and_wait(qtbot, view, valid)  # "Importar tudo": sorted into reports by content
    assert view.gate_passes
    assert view.pill.text.text() == S.STATUS_VALID
    assert view.next.isEnabled()
    view.next.click()
    assert view.current == ("locked", "03", "0")
    assert view.pill.text.text() == S.STATUS_LOCKED
    assert view.progress == S.RECENT_PROGRESS.format(done=17, total=18)


def test_acknowledge_warnings_from_the_pane(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, broken_scenarios: dict[str, Scenario]
) -> None:
    view = open_project(window, tmp_path / "p")
    import_and_wait(qtbot, view, list(broken_scenarios["S01_missing_month"].files))
    view.select(("report", "P04.01.L05"))
    (button,) = [b for b in view.pane.findChildren(QPushButton) if b.text() == S.ACKNOWLEDGE]
    button.click()
    assert view.states["P04.01.L05"].acknowledged
    assert S.ACKNOWLEDGE_DONE in [w.text() for w in view.pane.findChildren(QLabel)]
    assert "0 aviso" in view.counts.text()


def test_remove_a_duplicate(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, broken_scenarios: dict[str, Scenario]
) -> None:
    view = open_project(window, tmp_path / "p")
    import_and_wait(qtbot, view, list(broken_scenarios["V11_same_file"].files))
    view.select(("report", "P01.01.L03"))
    assert view.pill.text.text() == S.STATUS_WARNING
    duplicate = max(f.file_id for f in view.project.files("P01.01.L03"))
    view.report_page.remove_requested.emit(duplicate)
    assert view.pill.text.text() == S.STATUS_VALID


def test_footer_navigation(window: MainWindow, tmp_path: Path) -> None:
    view = open_project(window, tmp_path / "p")
    steps = view.substeps("02")
    assert view.current == steps[0]
    assert view.position.text() == S.SUBSTEP_OF.format(n=1, total=len(steps))
    view.next.click()
    assert view.current == steps[1]
    view.previous.click()
    view.previous.click()
    assert view.current == ("project",)


def test_icpc_codes_are_copied(window: MainWindow, tmp_path: Path) -> None:
    view = open_project(window, tmp_path / "p")
    view.select(("report", "P04.01.L01"))
    assert len(view.report_page.copy_buttons) == 3
    view.report_page.copy_buttons[2].click()
    text = QGuiApplication.clipboard().text()
    assert text.startswith("S74, S75")
    assert text.count(",") == 231
    assert view.report_page.copy_buttons[2].text() == S.COPIED


def test_edit_project_info_revalidates(
    qtbot: QtBot, window: MainWindow, tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    view = open_project(window, tmp_path / "p")
    import_and_wait(qtbot, view, [synthetic_fixtures["valid/P01.01.L03/2024-12"].path])
    view.select(("project",))
    view.project_page.unit.setText("USF Outra")
    view.project_page.save.click()
    assert view.states["P01.01.L03"].status is Status.ERROR
    assert view.title.text().startswith("USF Outra")


# ------------------------------------------------------------------- home and dialogs


def test_new_project_dialog_validates(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = NewProjectDialog("ANA SOUSA: M 01234")
    qtbot.addWidget(dialog)
    dialog.doctor.clear()
    assert not dialog.validate()
    assert dialog.unit_error.text() == S.FIELD_UNIT_REQUIRED
    assert dialog.doctor_error.text() == S.FIELD_DOCTOR_REQUIRED
    dialog.unit.setText("USF Exemplo")
    dialog.doctor.setText("ANA SOUSA: M 01234")
    dialog.folder.setText(str(tmp_path / "USF_Exemplo"))
    dialog.create_button.click()
    assert dialog.result_info is not None
    assert dialog.result_info.unit == "USF Exemplo"
    assert dialog.result_folder == tmp_path / "USF_Exemplo"
    assert len(dialog.result_info.years) == 1


def test_recent_projects(qtbot: QtBot, window: MainWindow, tmp_path: Path) -> None:
    view = open_project(window, tmp_path / "p")
    window.go_home()
    (card,) = window.home.findChildren(RecentCard)
    assert card.entry.name == INFO.title
    assert card.entry.progress == view.progress
    card.clicked.emit(card.entry.path)
    assert window.pages.currentWidget() is window.view
    assert window.title_bar.project_name.text().endswith(".mimufs")


def test_settings_dialog(qtbot: QtBot, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    dialog = SettingsDialog(store, check=lambda: None)
    qtbot.addWidget(dialog)
    dialog.check_now.click()
    qtbot.waitUntil(lambda: dialog.check_result.text() == S.UPDATE_NONE, timeout=5000)

    def offline() -> None:
        raise OSError("offline")

    failing = SettingsDialog(store, check=offline)  # type: ignore[arg-type]
    qtbot.addWidget(failing)
    failing.check_now.click()
    qtbot.waitUntil(lambda: failing.check_result.text() == S.UPDATE_FAILED, timeout=5000)
    dialog.doctor.setText("ANA SOUSA: M 01234")
    dialog.theme.setCurrentIndex(2)  # light
    dialog.updates.setChecked(False)
    with qtbot.waitSignal(dialog.theme_changed):
        dialog._save()
    saved = store.load()
    assert (saved.doctor_name, saved.theme, saved.update_check) == (
        "ANA SOUSA: M 01234",
        "light",
        False,
    )


def test_dictionary_manager_edits_medication(qtbot: QtBot, tmp_path: Path) -> None:
    dictionaries = Dictionaries(tmp_path / "dicionarios")
    dialog = DictionaryManager(dictionaries)
    qtbot.addWidget(dialog)
    tab = dialog.pages["medicamentos"]
    tab._add()
    row = tab.table.rowCount() - 1
    for col, value in enumerate(("tirzepatido", "analogo de GLP-1", "diabetes")):
        item = tab.table.item(row, col)
        assert item is not None
        item.setText(value)
    tab._save()
    assert dictionaries.medication_edited()
    assert dictionaries.table("medicamentos").height == 76
    assert not dialog.pages["icpc2"].editable
    tab.search.setText("tirzepatido")
    assert tab.count.text() == S.DICT_ROWS.format(shown=1, total=76)
