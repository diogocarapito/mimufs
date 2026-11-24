"""Format sniffing and first-sheet reading for MIM@UF exports (TECH_SPECS §5.0).

File extensions are never trusted (CLAUDE.md rule 8): MIM@UF names OOXML workbooks ``.xls``,
and users can rename anything. The first bytes decide the reader:

* ``PK\\x03\\x04`` (ZIP): OOXML workbook → openpyxl (+ :mod:`openpyxl_compat` patch)
* ``D0 CF 11 E0`` (OLE2): legacy BIFF ``.xls`` → xlrd
* anything else (HTML, CSV, PDF…): not an Excel file → check V01 🔴

Cells are returned as text without losing information (ints stay ``"65"``, floats keep their
decimal point, ``"65.0"``) because typing happens later, in staging, and the quality rules need
to know whether a decimal separator was present. Error messages never include cell contents.
"""

from __future__ import annotations

import datetime as dt
import io
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from mimufs.core.readers import openpyxl_compat

openpyxl_compat.apply()  # once, at reader import time (TECH_SPECS §5.0.1)

import openpyxl  # noqa: E402  (must come after the compat patch)
import xlrd  # noqa: E402

OOXML_MAGIC = b"PK\x03\x04"
BIFF_MAGIC = b"\xd0\xcf\x11\xe0"


class FileFormat(StrEnum):
    OOXML = "ooxml"
    BIFF = "biff"
    NOT_EXCEL = "not_excel"


#: Row ceilings of each real format (check V09: a file at the ceiling was probably truncated).
ROW_CEILING: dict[FileFormat, int] = {FileFormat.OOXML: 1_048_576, FileFormat.BIFF: 65_536}


class UnreadableFileError(Exception):
    """The file cannot be read as an Excel workbook (check V01).

    ``reason`` is a stable code (``not_excel``, ``corrupt``, ``no_sheets``); ``detail`` is safe
    to log: it never contains cell contents.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True, slots=True)
class SheetRows:
    """The first worksheet of a workbook, every cell as text ("" = blank)."""

    format: FileFormat
    sheet_name: str
    rows: tuple[tuple[str, ...], ...]  # all rows padded to the same width

    @property
    def max_row(self) -> int:
        """Rows physically present in the sheet (used by the truncation check V09)."""
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0


def sniff(path: Path) -> FileFormat:
    """Detect the real format of a file from its first bytes."""
    with path.open("rb") as fh:
        head = fh.read(8)
    if head.startswith(OOXML_MAGIC):
        return FileFormat.OOXML
    if head.startswith(BIFF_MAGIC):
        return FileFormat.BIFF
    return FileFormat.NOT_EXCEL


def read_first_sheet(path: Path) -> SheetRows:
    """Read the first worksheet of an Excel file, whatever its extension."""
    fmt = sniff(path)
    if fmt is FileFormat.OOXML:
        return _read_ooxml(path)
    if fmt is FileFormat.BIFF:
        return _read_biff(path)
    raise UnreadableFileError("not_excel", "file signature is not OOXML or BIFF")


# ---------------------------------------------------------------------------------- OOXML


def _read_ooxml(path: Path) -> SheetRows:
    data = path.read_bytes()
    try:
        with warnings.catch_warnings():
            # e.g. "Workbook contains no default style": harmless in MIM@UF exports.
            warnings.simplefilter("ignore", UserWarning)
            # A file object, not a path: openpyxl refuses paths ending in ".xls".
            wb = openpyxl.load_workbook(
                io.BytesIO(data), read_only=True, data_only=True, keep_links=False
            )
            try:
                if not wb.worksheets:
                    raise UnreadableFileError("no_sheets", "workbook has no worksheets")
                ws = wb.worksheets[0]
                # Read-only mode trusts the stored <dimension>, which exporters often get
                # wrong; resetting makes openpyxl read every row that is really there.
                ws.reset_dimensions()
                rows = _pad_rows(
                    tuple(_cell_text(v) for v in row) for row in ws.iter_rows(values_only=True)
                )
                name = ws.title
            finally:
                wb.close()
    except UnreadableFileError:
        raise
    except Exception as exc:  # BadZipFile, KeyError, InvalidFileException, ValueError…
        # from None: the original message may quote cell contents (patient data).
        raise UnreadableFileError("corrupt", type(exc).__name__) from None
    return SheetRows(FileFormat.OOXML, name, rows)


# ----------------------------------------------------------------------------------- BIFF


def _read_biff(path: Path) -> SheetRows:
    try:
        book = xlrd.open_workbook(file_contents=path.read_bytes(), on_demand=True)
        try:
            if book.nsheets == 0:
                raise UnreadableFileError("no_sheets", "workbook has no worksheets")
            sheet = book.sheet_by_index(0)
            rows = _pad_rows(
                tuple(_biff_cell_text(cell, book.datemode) for cell in sheet.row(r))
                for r in range(sheet.nrows)
            )
            name = sheet.name
        finally:
            book.release_resources()
    except UnreadableFileError:
        raise
    except Exception as exc:  # xlrd.XLRDError, struct.error, CompDocError…
        raise UnreadableFileError("corrupt", type(exc).__name__) from None
    return SheetRows(FileFormat.BIFF, name, rows)


def _biff_cell_text(cell: Any, datemode: int) -> str:
    ctype = cell.ctype
    if ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    if ctype == xlrd.XL_CELL_DATE:
        try:
            return _cell_text(xlrd.xldate_as_datetime(cell.value, datemode))
        except Exception:
            return _cell_text(cell.value)
    if ctype == xlrd.XL_CELL_NUMBER:
        # BIFF stores every number as a double; integral values were typed as integers.
        value = float(cell.value)
        return str(int(value)) if value.is_integer() else repr(value)
    if ctype == xlrd.XL_CELL_BOOLEAN:
        return "TRUE" if cell.value else "FALSE"
    if ctype == xlrd.XL_CELL_ERROR:
        return "#ERR"
    return str(cell.value)


# -------------------------------------------------------------------------------- helpers


def _cell_text(value: object) -> str:
    """Lossless text for an openpyxl cell value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, dt.datetime):
        if value.time() == dt.time(0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    return str(value)


def _pad_rows(rows: Iterable[tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    """Pad every row to the widest row and drop trailing fully blank rows."""
    materialised = list(rows)
    while materialised and not any(materialised[-1]):
        materialised.pop()
    width = max((len(r) for r in materialised), default=0)
    return tuple(r + ("",) * (width - len(r)) for r in materialised)
