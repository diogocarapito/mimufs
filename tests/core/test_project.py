"""Project storage, import, re-validation and statuses (TECH_SPECS §4, §7; PRD §6.1–6.3)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from mimufs.core.project import Project, ProjectError, ProjectInfo, default_name
from mimufs.core.readers.mimuf_header import read_mimuf_file
from mimufs.core.validation.result import Status
from tests.fixtures import make_fixtures as mf
from tests.fixtures.broken import Scenario

INFO = ProjectInfo(unit=mf.UNIT, doctor=mf.PROJECT_DOCTOR, years=(mf.YEAR,), description="Teste")


def new_project(tmp_path: Path, info: ProjectInfo = INFO) -> Project:
    return Project.create(tmp_path / "projeto", info)


def valid_paths(fixtures: dict[str, mf.Fixture], code: str | None = None) -> list[Path]:
    return [
        f.path for f in fixtures.values() if f.kind == "valid" and (code is None or f.code == code)
    ]


# ---------------------------------------------------------------------- create / open


def test_create_lays_out_the_folder(tmp_path: Path) -> None:
    project = new_project(tmp_path)
    assert project.db_path.name == f"{default_name(mf.UNIT, (mf.YEAR,))}.mimufs"
    assert {p.name for p in project.folder.iterdir()} >= {
        "raw",
        "exports",
        "logs",
        project.db_path.name,
    }
    info = project.info
    assert (info.unit, info.doctor, info.years, info.description) == (
        mf.UNIT, mf.PROJECT_DOCTOR, (mf.YEAR,), "Teste",
    )  # fmt: skip
    assert info.title == f"{mf.UNIT} · {mf.YEAR}"


def test_create_refuses_an_existing_project_and_an_empty_unit(tmp_path: Path) -> None:
    new_project(tmp_path)
    with pytest.raises(ProjectError, match="Já existe"):
        new_project(tmp_path)
    with pytest.raises(ProjectError, match="unidade"):
        Project.create(tmp_path / "outro", ProjectInfo(unit=" ", doctor="", years=(2024,)))


def test_open_by_file_or_folder(tmp_path: Path) -> None:
    project = new_project(tmp_path)
    assert Project.open(project.db_path).info.unit == mf.UNIT
    assert Project.open(project.folder).db_path == project.db_path
    with pytest.raises(ProjectError):
        Project.open(tmp_path / "nada")
    not_a_project = tmp_path / "x.mimufs"
    not_a_project.write_bytes(b"not a database")
    with pytest.raises(ProjectError, match="válido"):
        Project.open(not_a_project)


# --------------------------------------------------------------------------- import


def test_import_the_valid_set(tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    project = new_project(tmp_path)
    outcomes = project.import_paths(valid_paths(synthetic_fixtures))
    assert len(outcomes) == 44
    assert {o.status for o in outcomes} == {Status.VALID}
    assert all(o.slots for o in outcomes)
    overview = project.overview()
    for code, state in overview.items():
        if code.startswith("SCLINICO"):
            assert state.status is Status.PENDING
            assert not state.available  # waits for the PDF reader (TECH_SPECS §10.1)
            assert state.passes  # so it doesn't block the gate meanwhile
            continue
        assert state.status is Status.VALID, code
        assert state.filled == len(state.slots), code
        assert state.passes


def test_raw_copies_are_byte_identical(
    tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    project = new_project(tmp_path)
    path = synthetic_fixtures["variants/footer"].path
    (outcome,) = project.import_paths([path])
    (copy,) = list(project.raw_dir.iterdir())
    assert copy.read_bytes() == path.read_bytes()
    assert copy.name.startswith(hashlib.sha256(path.read_bytes()).hexdigest()[:12])
    (record,) = project.files()
    assert record.n_footer == 1  # footer removed from the data, kept in raw/ (V12)
    assert outcome.file_id == record.file_id


def test_stored_sheet_round_trips(
    tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    project = new_project(tmp_path)
    for name in ("valid/P02.01.R04/2024-12", "valid/P01.01.L03/2024-12", "variants/legacy_biff"):
        path = synthetic_fixtures[name].path
        (outcome,) = project.import_paths([path])
        assert outcome.file_id is not None
        stored = project.load_sheet(outcome.file_id)
        original = read_mimuf_file(path)
        assert stored.rows.equals(original.rows), name
        assert (stored.header, stored.header2, stored.pages, stored.filter) == (
            original.header, original.header2, original.pages, original.filter,
        ), name  # fmt: skip


def test_rejected_files_are_not_stored(
    tmp_path: Path, broken_scenarios: dict[str, Scenario]
) -> None:
    project = new_project(tmp_path)
    for name in ("V01_html", "V01_corrupt", "V01_no_header", "V02_unknown"):
        sc = broken_scenarios[name]
        (outcome,) = project.import_paths(list(sc.files))
        assert outcome.file_id is None
        assert outcome.status is Status.ERROR
        ((cid, severity),) = sc.expect
        assert [(i.check_id, i.severity) for i in outcome.issues] == [(cid, severity)]
        assert sc.contains[0] in outcome.issues[0].message
    assert project.files() == []
    assert list(project.raw_dir.iterdir()) == []


def test_file_dropped_on_the_wrong_report(
    tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    project = new_project(tmp_path)
    path = synthetic_fixtures["valid/P01.01.L03/2024-12"].path
    (outcome,) = project.import_paths([path], expected_code="P01.01.L01")
    assert outcome.file_id is None
    assert outcome.issues[0].check_id == "V02"
    assert "é o P01.01.L03" in outcome.issues[0].message
    assert "não o P01.01.L01" in outcome.issues[0].message
    (ok,) = project.import_paths([path], expected_code="P01.01.L03")
    assert ok.status is Status.VALID


def test_sclinico_files_wait_for_the_pdf_reader(
    tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    project = new_project(tmp_path)
    outcomes = project.import_paths(
        [synthetic_fixtures["sclinico/pdf"].path, synthetic_fixtures["sclinico/csv"].path]
    )
    assert {(o.code, o.file_id, o.issues[0].check_id) for o in outcomes} == {
        ("SCLINICO.consultas", None, "V01")
    }


def test_folders_are_imported_recursively(
    tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    project = new_project(tmp_path)
    folder = synthetic_fixtures["valid/P04.01.L05/2024-01"].path.parent
    outcomes = project.import_paths([folder])
    assert len(outcomes) == 12
    assert project.report_state("P04.01.L05").status is Status.VALID


# ------------------------------------------------------------- broken scenarios via storage


def test_broken_scenarios_through_the_project(
    tmp_path: Path, broken_scenarios: dict[str, Scenario]
) -> None:
    """Same expectations as the pure checks, after storage in DuckDB and re-validation."""
    failures = {}
    for name, sc in broken_scenarios.items():
        if sc.code is None:
            continue
        project = Project.create(tmp_path / name, INFO)
        project.import_paths(list(sc.files))
        state = project.report_state(sc.code)
        got = {(i.check_id, i.severity) for i in state.issues}
        if got != sc.expect:
            failures[name] = (sorted(got), sorted(sc.expect))
        expected_status = max((s for _, s in sc.expect), default=Status.VALID)
        if state.status is not expected_status:
            failures[name + " status"] = (state.status, expected_status)
    assert failures == {}


def test_partly_covered_quarter_is_incomplete(
    tmp_path: Path, broken_scenarios: dict[str, Scenario]
) -> None:
    project = new_project(tmp_path)
    sc = broken_scenarios["S01_coverage_gap"]  # T3 missing
    feb_only = broken_scenarios["S01_coverage_overlap"].files[-1]  # a monthly file for Feb
    project.import_paths([p for p in sc.files if "T1" not in p.name] + [feb_only])
    tiles = {s.slot.label: s.status for s in project.report_state("P06.01.01.L03").slots}
    assert tiles == {
        "T1": Status.WARNING,
        "T2": Status.VALID,
        "T3": Status.PENDING,
        "T4": Status.VALID,
    }


# ----------------------------------------------------------------- decisions / re-validation


def test_remove_file_revalidates(tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    project = new_project(tmp_path)
    project.import_paths(valid_paths(synthetic_fixtures, "P10.01.L01"))
    victim = next(f for f in project.files("P10.01.L01") if "altura" in f.original_name)
    project.remove_file(victim.file_id)
    state = project.report_state("P10.01.L01")
    assert state.status is Status.WARNING
    assert [i.message for i in state.issues] == ["Falta 1 extração: Altura."]
    assert any(victim.sha256[:12] in p.name for p in project.raw_dir.iterdir())  # copy kept


def test_acknowledge_warnings_until_they_change(
    tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    project = new_project(tmp_path)
    paths = valid_paths(synthetic_fixtures, "P04.01.L05")
    project.import_paths(paths[:10])
    state = project.report_state("P04.01.L05")
    assert (state.status, state.passes) == (Status.WARNING, False)
    project.acknowledge("P04.01.L05", "meses em falta")
    assert project.report_state("P04.01.L05").passes
    project.import_paths(paths[10:11])  # the warnings change: confirm again
    state = project.report_state("P04.01.L05")
    assert (state.status, state.acknowledged, state.passes) == (Status.WARNING, False, False)


def test_errors_cannot_be_acknowledged(
    tmp_path: Path, broken_scenarios: dict[str, Scenario]
) -> None:
    project = new_project(tmp_path)
    project.import_paths(list(broken_scenarios["V06_other_doctor"].files))
    with pytest.raises(ProjectError, match="erros"):
        project.acknowledge("P04.01.L05")


def test_skip_optional_reports_only(tmp_path: Path) -> None:
    project = new_project(tmp_path)
    project.set_skipped("P04.R06", True)
    state = project.report_state("P04.R06")
    assert (state.status, state.passes) == (Status.SKIPPED, True)
    with pytest.raises(ProjectError, match="obrigatório"):
        project.set_skipped("P01.01.L01", True)
    project.set_skipped("P04.R06", False)
    assert project.report_state("P04.R06").status is Status.PENDING


def test_optional_pending_reports_do_not_block(tmp_path: Path) -> None:
    project = new_project(tmp_path)
    assert project.report_state("P04.R06").passes  # optional
    assert not project.report_state("P01.01.L01").passes  # required


def test_changing_the_unit_revalidates(
    tmp_path: Path, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    project = new_project(tmp_path)
    project.import_paths(valid_paths(synthetic_fixtures, "P01.01.L03"))
    project.update_info(unit="USF Outra")
    state = project.report_state("P01.01.L03")
    assert [(i.check_id, i.severity) for i in state.issues] == [("V03", Status.ERROR)]
    project.update_info(unit=mf.UNIT)
    assert project.report_state("P01.01.L03").status is Status.VALID


def test_event_log(tmp_path: Path, broken_scenarios: dict[str, Scenario]) -> None:
    project = new_project(tmp_path)
    project.import_paths(list(broken_scenarios["V05_filter_vs_pages"].files))
    kinds = [kind for _, kind, _, _ in project.events()]
    assert "OK" in kinds
    assert "V05" in kinds
    for _, _, _, message in project.events():
        assert "900" not in message  # no SNS numbers in the log
