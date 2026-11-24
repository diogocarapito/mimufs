"""Format sniffing and first-sheet reading (TECH_SPECS §5.0, check V01 inputs)."""

from __future__ import annotations

import datetime as dt
import re
import zipfile
from pathlib import Path

import openpyxl
import pytest
import xlwt

from mimufs.core.readers import openpyxl_compat
from mimufs.core.readers.excel import (
    ROW_CEILING,
    FileFormat,
    UnreadableFileError,
    read_first_sheet,
    sniff,
)

ROWS: list[list[object]] = [
    ["P01.01.L01. Inscritos &gt; Utente"],
    [],
    ["Filtro do relatório:"],
    ["(Mês = 2024-01) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)"],
    [],
    ["NOP", "Utente", None, "Idade", "Valor", "Data"],
    ["N1", "123456789", "Utente 0001", 65, 6.5, dt.datetime(2024, 3, 1)],
    ["N2", "987654321", "Utente 0002", 70, 65.0, dt.date(2024, 4, 2)],
]


def _write_xlsx(path: Path, rows: list[list[object]] = ROWS) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Relatório"
    for row in rows:
        ws.append(row)
    with path.open("wb") as fh:  # file handle: openpyxl refuses to *save* to ".xls" too
        wb.save(fh)
    return path


def _write_biff(path: Path) -> Path:
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Relatorio")
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    for r, row in enumerate(ROWS):
        for c, value in enumerate(row):
            if value is None:
                continue
            if isinstance(value, dt.date):
                ws.write(r, c, value, date_style)
            else:
                ws.write(r, c, value)
    wb.save(str(path))
    return path


@pytest.mark.parametrize("suffix", [".xls", ".xlsx", ".dat"])
def test_ooxml_read_whatever_the_extension(tmp_path: Path, suffix: str) -> None:
    path = _write_xlsx(tmp_path / f"export{suffix}")
    assert sniff(path) is FileFormat.OOXML
    sheet = read_first_sheet(path)
    assert sheet.format is FileFormat.OOXML
    assert sheet.sheet_name == "Relatório"
    assert sheet.max_row == len(ROWS)
    assert all(len(r) == sheet.width == 6 for r in sheet.rows)
    assert sheet.rows[1] == ("",) * 6  # blank rows are kept
    assert sheet.rows[6] == ("N1", "123456789", "Utente 0001", "65", "6.5", "2024-03-01")
    # The text is what the file stores: openpyxl wrote the float 65.0 as <v>65</v>.
    assert sheet.rows[7][3:6] == ("70", "65", "2024-04-02")


def test_stored_decimal_point_is_kept(tmp_path: Path) -> None:
    """A value stored as "65.0" must not lose its decimal point (quality rules use it)."""
    good = _write_xlsx(tmp_path / "good.xlsx")
    edited = tmp_path / "edited.xls"
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(edited, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data, n = re.subn(rb"<v>65</v>", b"<v>65.0</v>", data)
                assert n == 2  # Idade 65 (row 7) and Valor 65 (row 8)
            dst.writestr(item, data)
    sheet = read_first_sheet(edited)
    assert sheet.rows[6][3] == "65.0"
    assert sheet.rows[7][4] == "65.0"


def test_wrong_dimension_tag_still_reads_every_row(tmp_path: Path) -> None:
    """Exporters often write a wrong <dimension>; read-only openpyxl would trust it."""
    good = _write_xlsx(tmp_path / "good.xlsx")
    bad = tmp_path / "bad_dimension.xls"
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(bad, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data, n = re.subn(rb'<dimension ref="[^"]+"', b'<dimension ref="A1"', data)
                assert n == 1
            dst.writestr(item, data)
    sheet = read_first_sheet(bad)
    assert sheet.max_row == len(ROWS)
    assert sheet.rows[6][1] == "123456789"


def test_legacy_biff(tmp_path: Path) -> None:
    path = _write_biff(tmp_path / "legacy.xls")
    assert sniff(path) is FileFormat.BIFF
    sheet = read_first_sheet(path)
    assert sheet.format is FileFormat.BIFF
    assert sheet.rows[6] == ("N1", "123456789", "Utente 0001", "65", "6.5", "2024-03-01")
    assert sheet.rows[7][4] == "65"  # BIFF has no int/float distinction


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"<html><table><tr><td>NOP</td></tr></table></html>", "not_excel"),
        (b"NOP;Utente\nN1;123456789\n", "not_excel"),
        (b"", "not_excel"),
        (b"%PDF-1.4\n", "not_excel"),
        (b"PK\x03\x04 this is not really a zip", "corrupt"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100, "corrupt"),
    ],
)
def test_unreadable_files(tmp_path: Path, content: bytes, reason: str) -> None:
    path = tmp_path / "relatorio.xls"
    path.write_bytes(content)
    with pytest.raises(UnreadableFileError) as info:
        read_first_sheet(path)
    assert info.value.reason == reason


def test_zip_that_is_not_a_workbook(tmp_path: Path) -> None:
    path = tmp_path / "relatorio.xls"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("hello.txt", "123456789")
    with pytest.raises(UnreadableFileError) as info:
        read_first_sheet(path)
    assert info.value.reason == "corrupt"
    assert "123456789" not in str(info.value)  # never leak contents into messages/logs


def test_row_ceilings() -> None:
    assert ROW_CEILING[FileFormat.OOXML] == 1_048_576
    assert ROW_CEILING[FileFormat.BIFF] == 65_536


# ------------------------------------------------------------------------- compat patch


def test_compat_patch_is_applied_and_idempotent() -> None:
    assert openpyxl_compat.is_applied()
    openpyxl_compat.apply()
    assert openpyxl_compat.is_applied()


def test_compat_patch_refuses_other_openpyxl_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openpyxl_compat, "_applied", False)
    monkeypatch.setattr(openpyxl, "__version__", "9.9.9")
    with pytest.raises(openpyxl_compat.OpenpyxlVersionError):
        openpyxl_compat.apply()


@pytest.mark.needs_input
@pytest.mark.xfail(
    strict=True,
    reason="Needs Diogo's openpyxl.worksheet._reader patch and a fixture with the MIM@UF quirk",
)
def test_mimuf_quirk_needs_patch() -> None:
    """Must fail without the patch and pass with it (TECH_SPECS §5.0.1)."""
    raise NotImplementedError("openpyxl compat patch not ported yet")
