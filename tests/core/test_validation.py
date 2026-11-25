"""Checks V01–V12 and S01–S04 (PRD §6.3.2) on the valid and the deliberately broken fixtures."""

from __future__ import annotations

import dataclasses
import hashlib
import string
from pathlib import Path

import pytest

from mimufs.core.readers.excel import ROW_CEILING, FileFormat, UnreadableFileError
from mimufs.core.readers.mimuf_header import HeaderParseError, RawSheet, read_mimuf_file
from mimufs.core.specs import mimuf_specs
from mimufs.core.validation import messages as M
from mimufs.core.validation.checks import check_file, column_letter, id_counts
from mimufs.core.validation.context import ProjectCtx
from mimufs.core.validation.result import Issue, Status, worst
from mimufs.core.validation.set_checks import ReportFile, check_report
from mimufs.core.validation.slots import expected_slots
from tests.fixtures import make_fixtures as mf
from tests.fixtures.broken import Scenario

SPECS = mimuf_specs()
CTX = ProjectCtx(unit=mf.UNIT, doctor=mf.PROJECT_DOCTOR, years=(mf.YEAR,))


def run_report(code: str, paths: list[Path], ctx: ProjectCtx = CTX) -> list[Issue]:
    """File checks + report checks for the files of one report, as the project will run them."""
    spec = SPECS[code]
    issues: list[Issue] = []
    files: list[ReportFile] = []
    for i, path in enumerate(paths):
        raw = read_mimuf_file(path)
        result = check_file(raw, spec, ctx, path.name, i)
        issues += result.issues
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(ReportFile(i, path.name, sha, raw, result.placement))
    return issues + check_report(spec, files, ctx)


# ---------------------------------------------------------------------- valid fixtures


def test_every_valid_report_has_no_issues(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    by_code: dict[str, list[Path]] = {}
    for f in synthetic_fixtures.values():
        if f.kind == "valid" and f.code:
            by_code.setdefault(f.code, []).append(f.path)
    assert set(by_code) == set(SPECS)
    problems = {
        code: [(i.check_id, i.message) for i in run_report(code, paths)]
        for code, paths in by_code.items()
    }
    assert {k: v for k, v in problems.items() if v} == {}


def test_valid_files_fill_their_slots(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    for f in synthetic_fixtures.values():
        if f.kind != "valid" or f.code is None:
            continue
        spec = SPECS[f.code]
        placement = check_file(read_mimuf_file(f.path), spec, CTX, f.path.name).placement
        keys = {s.key for s in expected_slots(spec, CTX.years)}
        assert placement.slot_keys, f.name
        assert set(placement.slot_keys) <= keys, f.name


# ------------------------------------------------------------------- broken fixtures


def test_broken_fixtures_produce_exactly_the_expected_issues(
    broken_scenarios: dict[str, Scenario],
) -> None:
    """The M1 "Done when", at the core level: each scenario → the right statuses and texts."""
    failures: dict[str, str] = {}
    for name, sc in broken_scenarios.items():
        if sc.code is None:
            continue  # rejected at import: see test_import_level_scenarios
        issues = run_report(sc.code, list(sc.files))
        got = {(i.check_id, i.severity) for i in issues}
        text = " | ".join(i.message for i in issues)
        missing = [c for c in sc.contains if c not in text]
        if got != sc.expect or missing:
            failures[name] = f"got {sorted(got)}, expected {sorted(sc.expect)}, missing {missing}"
    assert failures == {}


def test_every_check_has_a_triggering_fixture(broken_scenarios: dict[str, Scenario]) -> None:
    triggered = {cid for sc in broken_scenarios.values() for cid, _ in sc.expect}
    # V09 needs a 1,048,576-row sheet: covered by test_truncated_sheet below instead.
    expected = {f"V{n:02d}" for n in range(1, 12) if n != 9} | {"S01", "S02", "S03", "S04"}
    assert expected <= triggered


def test_import_level_scenarios(broken_scenarios: dict[str, Scenario]) -> None:
    for name in ("V01_html", "V01_corrupt", "V01_no_header"):
        with pytest.raises((UnreadableFileError, HeaderParseError)):
            read_mimuf_file(broken_scenarios[name].files[0])
    unknown = read_mimuf_file(broken_scenarios["V02_unknown"].files[0])
    assert unknown.spec is None


def test_issues_say_what_where_and_how(broken_scenarios: dict[str, Scenario]) -> None:
    for sc in broken_scenarios.values():
        if sc.code is None:
            continue
        for issue in run_report(sc.code, list(sc.files)):
            assert issue.message.strip(), issue
            assert issue.fix_hint, issue
            if issue.check_id.startswith("V"):
                assert issue.location, issue
                assert issue.file_id is not None, issue


def test_footer_is_removed_without_an_issue(broken_scenarios: dict[str, Scenario]) -> None:
    sc = broken_scenarios["V12_footer"]
    mutated = next(p for p in sc.files if p.name == sc.mutated)
    assert len(read_mimuf_file(mutated).footer_rows) == 1
    assert run_report("P01.01.L03", list(sc.files)) == []


def test_ids_counted_for_info_card(broken_scenarios: dict[str, Scenario]) -> None:
    sc = broken_scenarios["V10_ids"]
    mutated = next(p for p in sc.files if p.name == sc.mutated)
    raw = read_mimuf_file(mutated)
    assert id_counts(check_file(raw, SPECS["P10.01.L01"], CTX, "x").bound) == (2, 1)


# ------------------------------------------------------------------------- unit tests


def test_truncated_sheet(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    """V09 🔴 at the format's row ceiling (OOXML 1,048,576; legacy BIFF 65,536)."""
    raw = read_mimuf_file(synthetic_fixtures["valid/P01.01.L03/2024-12"].path)
    for fmt in (FileFormat.OOXML, FileFormat.BIFF):
        cut: RawSheet = dataclasses.replace(raw, format=fmt, max_row=ROW_CEILING[fmt])
        issues = check_file(cut, SPECS["P01.01.L03"], CTX, "grande.xls").issues
        assert [(i.check_id, i.severity) for i in issues] == [("V09", Status.ERROR)]
        assert "provavelmente cortada" in issues[0].message
    below = dataclasses.replace(
        raw, max_row=ROW_CEILING[FileFormat.BIFF] - 1, format=FileFormat.BIFF
    )
    assert check_file(below, SPECS["P01.01.L03"], CTX, "x").issues == ()


def test_wrong_project_unit_flags_every_file(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    ctx = ProjectCtx(unit="USF Outra", doctor="", years=(mf.YEAR,))
    raw = read_mimuf_file(synthetic_fixtures["valid/P02.01.R01/2024-12"].path)  # unit in a column
    issues = check_file(raw, SPECS["P02.01.R01"], ctx, "x").issues
    assert [(i.check_id, i.severity) for i in issues] == [("V03", Status.ERROR)]
    assert "coluna A" in (issues[0].location or "")


def test_expected_slots_per_kind() -> None:
    def labels(code: str, years: tuple[int, ...] = (2024,)) -> list[str]:
        return [s.label for s in expected_slots(SPECS[code], years)]

    assert labels("P01.01.L01") == ["Jan", "Dez"]
    assert len(labels("P04.01.L05")) == 12
    assert labels("P06.01.01.L03") == ["T1", "T2", "T3", "T4"]
    assert labels("P10.01.L01") == ["Peso", "Altura", "PAs", "PAd", "DM desde"]
    assert labels("P07.01.01.L01") == ["2024"]
    icpc = expected_slots(SPECS["P04.01.L01"], (2024,))
    assert [s.label for s in icpc] == ["Lote 1", "Lote 2", "Lote 3"]
    assert icpc[2].detail == "S74 → Z29 · 232 códigos"
    assert labels("P01.01.L01", (2023, 2024)) == ["Jan 2023", "Dez 2023", "Jan 2024", "Dez 2024"]


def test_project_ctx_name_matching() -> None:
    ctx = ProjectCtx(unit="USF São João", doctor="ANA SOUSA: M 01234", years=(2024,))
    assert ctx.same_unit("usf sao  joão")
    assert not ctx.same_unit("USF São Jorge")
    assert ctx.is_project_doctor("Ana Sousa")
    assert ctx.is_project_doctor("ANA SOUSA: M 01234")
    assert not ctx.is_project_doctor("RUI SOUSA: M 01234")
    with pytest.raises(ValueError, match="1 or 2"):
        ProjectCtx(unit="x", doctor="", years=(2022, 2023, 2024))


def test_every_message_template_renders() -> None:
    for key, (message, hint) in M.TEMPLATES.items():
        fields = {
            f
            for text in (message, hint or "")
            for _, f, _, _ in string.Formatter().parse(text)
            if f
        }
        values = dict.fromkeys(fields, "x")
        rendered, rendered_hint = M.text(key, **values)
        assert "{" not in rendered, key
        assert rendered_hint is None or "{" not in rendered_hint, key


def test_status_ordering_and_issue_severity() -> None:
    assert worst([Status.VALID, Status.WARNING, Status.PENDING]) is Status.WARNING
    assert worst([], Status.PENDING) is Status.PENDING
    with pytest.raises(ValueError, match="warning or an error"):
        Issue("V00", Status.VALID, "x")


def test_column_letters() -> None:
    assert [column_letter(i) for i in (0, 1, 25, 26, 27, 51, 52)] == [
        "A", "B", "Z", "AA", "AB", "AZ", "BA",
    ]  # fmt: skip
    assert M.month_label("2024-07") == "Jul 2024"
    assert M.listing([str(i) for i in range(20)], limit=3) == "0, 1, 2, … (+17)"
