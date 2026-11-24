"""The synthetic fixtures parse back to the report, slot and rows they were generated for.

These files feed the M1 checks and the offline e2e test, so a generator bug would hide parser
bugs. Each valid file must look like a correct extraction: right report, slot, unit, Páginas.
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl
import pytest

from mimufs.core.readers import java_runtime, sclinico_pdf, tabula_runner
from mimufs.core.readers.excel import FileFormat, UnreadableFileError
from mimufs.core.readers.mimuf_header import RawSheet, bind_columns, is_total, read_mimuf_file
from mimufs.core.specs import mimuf_specs
from mimufs.core.specs.loader import load_icpc_batches
from mimufs.core.specs.models import (
    IcpcSetsSlots,
    MimufReportSpec,
    MonthCoverageSlots,
    MonthsSlots,
    ValuesSlots,
    YearSlots,
)
from tests.fixtures import make_fixtures as mf

SPECS = mimuf_specs()
VALID = sorted(
    f"valid/{code}/{fill.slot}" for code, spec in SPECS.items() for fill in mf.slot_fills(spec)
)


def _raw(fixtures: dict[str, mf.Fixture], name: str) -> RawSheet:
    return read_mimuf_file(fixtures[name].path)


def test_every_slot_of_every_report_has_a_valid_file(
    synthetic_fixtures: dict[str, mf.Fixture],
) -> None:
    valid = {name for name, f in synthetic_fixtures.items() if f.kind == "valid"}
    assert valid == set(VALID)
    assert {f.code for f in synthetic_fixtures.values() if f.kind == "valid"} == set(SPECS)


def _expected_slot(raw: RawSheet, spec: MimufReportSpec) -> str | None:
    """The slot the file covers, derived only from the parsed metadata (as M1 will)."""
    slots = spec.slots
    year = str(mf.YEAR)
    if isinstance(slots, MonthsSlots):
        (month,) = raw.effective("mes")
        return month
    if isinstance(slots, MonthCoverageSlots):
        if slots.display == "quarters":
            (quarter,) = raw.effective("trimestre")
            return quarter
        months = sorted(raw.effective("mes"))
        return f"{months[0]}..{months[-1][-2:]}"
    if isinstance(slots, YearSlots):
        (ano,) = raw.effective("ano")
        return ano
    if isinstance(slots, ValuesSlots):
        (value,) = raw.effective(slots.filter_key)
        (slot,) = slots.match(value)
        return slot
    if isinstance(slots, IcpcSetsSlots):
        codes = raw.icpc_codes()
        batches = load_icpc_batches(slots.sets_file).batches
        (n,) = [b.n for b in batches if set(b.codes) == codes]
        return f"set{n}"
    raise AssertionError(year)


@pytest.mark.parametrize("name", VALID)
def test_valid_file_parses_to_its_report_and_slot(
    name: str, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    fixture = synthetic_fixtures[name]
    raw = _raw(synthetic_fixtures, name)
    assert (raw.code, raw.code_source) == (fixture.code, "title")
    assert raw.format is FileFormat.OOXML
    spec = raw.spec
    assert spec is not None
    bound = bind_columns(raw, spec)
    assert bound.mismatches == ()
    assert bound.extra_columns == ()
    assert raw.n_rows == fixture.n_rows
    assert raw.n_rows > 0, "every valid file has data"
    assert raw.footer_rows == ()
    assert _expected_slot(raw, spec) == fixture.slot

    unit_cols = spec.header.by_role("unit")
    column_units = bound.data[unit_cols[0].name].to_list() if unit_cols else []
    assert raw.effective("unidade", column_units) == (mf.UNIT,)

    for key, expected in spec.pages_expect.items():
        assert raw.page(key) == expected, key
    for key, expected in spec.filter_expect.items():
        wanted = expected.replace("{ano}", str(mf.YEAR))
        assert wanted in raw.effective(key) or raw.page(key) == wanted, key
    for key in spec.doctor_pages:
        page = raw.page(key)
        assert page is not None
        assert is_total(page) or page == mf.PROJECT_DOCTOR


def test_icpc_sets_cover_the_target_list(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    covered: set[str] = set()
    for name in VALID:
        if name.startswith("valid/P04.01.L01/"):
            covered |= _raw(synthetic_fixtures, name).icpc_codes()
    assert covered == load_icpc_batches().target  # S02 holds on the valid set


def test_reports_share_one_population(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    def sns(name: str) -> set[str]:
        raw = _raw(synthetic_fixtures, name)
        assert raw.spec is not None
        return set(bind_columns(raw, raw.spec).data["Utente"].drop_nulls().to_list())

    january = sns(f"valid/P01.01.L01/{mf.YEAR}-01")
    december = sns(f"valid/P01.01.L01/{mf.YEAR}-12")
    assert january != december, "some patients join or leave during the year"
    assert sns("valid/P10.01.L01/peso") <= december
    assert sns("valid/P07.03.01.L01/hba1c") == sns("valid/P10.01.L01/dm_desde")
    assert sns(f"valid/P06.01.01.L03/{mf.YEAR}-T1") <= january | december


def test_identifiers_are_obviously_synthetic(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    for name in VALID:
        raw = _raw(synthetic_fixtures, name)
        assert raw.spec is not None
        data = bind_columns(raw, raw.spec).data
        if "Utente" in data.columns:
            assert all(re.fullmatch(r"9\d{8}", v) for v in data["Utente"].to_list()), name
        if "Nome" in data.columns:
            assert all(re.fullmatch(r"Utente \d{4}", v) for v in data["Nome"].to_list()), name


def test_generation_is_deterministic(tmp_path: Path) -> None:
    first = mf.generate(tmp_path / "a")
    second = mf.generate(tmp_path / "b")
    assert (tmp_path / "a" / "manifest.json").read_text() == (
        tmp_path / "b" / "manifest.json"
    ).read_text()
    for name in ("valid/P06.01.01.L03/2024-T2", "valid/P10.01.L01/pas"):
        a, b = read_mimuf_file(first[name].path), read_mimuf_file(second[name].path)
        assert a.rows.equals(b.rows)
        assert a.filter_text == b.filter_text


# ----------------------------------------------------------------------------------- variants


def test_legacy_biff_matches_the_ooxml_file(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    biff = _raw(synthetic_fixtures, "variants/legacy_biff")
    ooxml = _raw(synthetic_fixtures, f"valid/P01.01.L01/{mf.YEAR}-12")
    assert biff.format is FileFormat.BIFF
    assert biff.code == "P01.01.L01"
    assert biff.filter_text == ooxml.filter_text
    assert biff.rows.drop("_row").equals(ooxml.rows.drop("_row"))


def test_xlsx_extension_reads_the_same(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    fixture = synthetic_fixtures["variants/xlsx"]
    assert fixture.path.suffix == ".xlsx"
    raw = read_mimuf_file(fixture.path)
    assert raw.rows.equals(_raw(synthetic_fixtures, "valid/P10.01.L01/altura").rows)


def test_footer_variant(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    raw = _raw(synthetic_fixtures, "variants/footer")
    assert raw.n_rows == synthetic_fixtures["variants/footer"].n_rows
    (footer,) = raw.footer_rows
    assert footer[0] == "Total"


def test_html_renamed_xls_is_not_excel(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    fixture = synthetic_fixtures["variants/not_excel"]
    assert fixture.path.suffix == ".xls"
    with pytest.raises(UnreadableFileError) as info:
        read_mimuf_file(fixture.path)
    assert info.value.reason == "not_excel"


def test_damaged_title_variant(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    raw = _raw(synthetic_fixtures, "variants/damaged_title")
    assert raw.title_raw.startswith("1.01.L03.")
    assert (raw.code, raw.code_source) == ("P01.01.L03", "title_text")
    assert raw.n_rows == synthetic_fixtures["variants/damaged_title"].n_rows


# ----------------------------------------------------------------------------------- SClínico


def test_sclinico_csv_fallback_reads(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    fixture = synthetic_fixtures["sclinico/csv"]
    frame = sclinico_pdf.read_appointments(fixture.path)
    assert frame.columns == list(sclinico_pdf.OUTPUT_COLUMNS)
    assert frame.height == fixture.n_rows
    assert frame["data_consulta"].dtype == pl.Date
    assert frame["data_consulta"].null_count() == 0
    assert frame["data_consulta"].dt.year().unique().to_list() == [mf.YEAR]


@pytest.mark.requires_java
@pytest.mark.skipif(java_runtime.find_java() is None, reason="no Java runtime on this machine")
def test_sclinico_style_pdf_reads_with_tabula(synthetic_fixtures: dict[str, mf.Fixture]) -> None:
    fixture = synthetic_fixtures["sclinico/pdf"]
    tables = tabula_runner.read_pdf_tables(
        fixture.path, lattice=True, pandas_options={"dtype": str}
    )
    assert sum(len(t) for t in tables) == fixture.n_rows
    assert all(t.shape[1] == len(mf.SCLINICO_PDF_HEADER) for t in tables)
