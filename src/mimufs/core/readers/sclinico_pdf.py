"""SClínico "Lista de consultas realizadas": PDF (tabula) or CSV fallback (TECH_SPECS §10.1).

Output contract (same for both inputs, so the rest of the pipeline never changes):

=================  ===========================================  =========
column             content                                      required
=================  ===========================================  =========
``data_consulta``  appointment date (``pl.Date``)               yes
``utente``         SNS number (text)                            yes
``nop``            operational patient number (text)            yes
``profissional``   professional's name (text)                   yes
``tipo_consulta``  raw appointment type (text; mapped in step 4) yes
``local``          place (text)                                 no
=================  ===========================================  =========

TODO(Diogo): the PDF path. His working ``tabula.read_pdf(...)`` call and the cleanup of its
result (options, column names, removal of repeated page headers) are ported **unchanged** into
:func:`read_pdf` via :func:`tabula_runner.read_pdf_tables`. Until then the PDF test is xfail and
users can use the CSV fallback.
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

import polars as pl

OUTPUT_COLUMNS = ("data_consulta", "utente", "nop", "profissional", "tipo_consulta", "local")
REQUIRED_COLUMNS = OUTPUT_COLUMNS[:5]
PDF_MAGIC = b"%PDF-"

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d")


class SclinicoReadError(ValueError):
    """The appointments file cannot be used. ``reason`` is a stable code; safe to log."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def read_appointments(path: Path) -> pl.DataFrame:
    """Read an appointments PDF or CSV into the output contract."""
    with path.open("rb") as fh:
        head = fh.read(5)
    if head == PDF_MAGIC:
        return read_pdf(path)
    return read_csv(path)


def read_pdf(path: Path) -> pl.DataFrame:
    raise NotImplementedError(
        "SClínico PDF reading waits for Diogo's tabula.read_pdf script (TECH_SPECS §10.1)"
    )


def _normalise_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SclinicoReadError("encoding", "not UTF-8 or Windows-1252")


def read_csv(path: Path) -> pl.DataFrame:
    """The manual fallback: a CSV (``;`` or ``,``) with the contract's columns."""
    text = _decode(path.read_bytes())
    first_line = text.splitlines()[0] if text.strip() else ""
    if not first_line:
        raise SclinicoReadError("empty")
    separator = ";" if first_line.count(";") > first_line.count(",") else ","
    try:
        frame = pl.read_csv(io.StringIO(text), separator=separator, infer_schema=False)
    except Exception as exc:  # polars ComputeError etc.; message may quote file contents
        raise SclinicoReadError("unparseable", type(exc).__name__) from None
    frame = frame.rename({c: _normalise_name(c) for c in frame.columns})
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise SclinicoReadError("missing_columns", ", ".join(missing))
    if "local" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Utf8).alias("local"))
    frame = frame.select(
        [pl.col(c).cast(pl.Utf8).str.strip_chars().alias(c) for c in OUTPUT_COLUMNS]
    )
    return frame.with_columns(_parse_date(pl.col("data_consulta")).alias("data_consulta"))


def _parse_date(column: pl.Expr) -> pl.Expr:
    parsed = [column.str.strptime(pl.Date, fmt, strict=False) for fmt in _DATE_FORMATS]
    return pl.coalesce(parsed)
