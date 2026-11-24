"""Synthetic MIM@UF-style fixtures. No real patient data, ever (CLAUDE.md rule 2).

Usage:  uv run python tests/fixtures/make_fixtures.py [OUT_DIR]
Default OUT_DIR: tests/fixtures/generated/ (git-ignored). Tests call :func:`generate` into a
temporary directory instead, so they never depend on a previous manual run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADER_EXAMPLES = REPO_ROOT / "docs" / "reference" / "MIMUF_Header_examples.xlsx"
DEFAULT_OUT = Path(__file__).resolve().parent / "generated"


def _save(wb: openpyxl.Workbook, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:  # a handle: openpyxl refuses to save to a ".xls" path
        wb.save(fh)
    return path


def header_example_rows() -> dict[str, list[list[object]]]:
    """Cell values of every sheet of the real header workbook, keyed by report code."""
    wb = openpyxl.load_workbook(HEADER_EXAMPLES, data_only=True)
    try:
        return {
            ws.title: [list(row) for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets
        }
    finally:
        wb.close()


def write_rows(path: Path, rows: list[list[object]], sheet_title: str = "Relatório") -> Path:
    """Write rows to an OOXML workbook (any extension; MIM@UF uses ``.xls``)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet_title
    for row in rows:
        ws.append(row)
    return _save(wb, path)


def split_header_examples(out_dir: Path) -> dict[str, Path]:
    """Save each sheet of the header workbook as its own ``<code>.xls`` (OOXML) file."""
    return {
        code: write_rows(out_dir / "header_examples" / f"{code}.xls", rows)
        for code, rows in header_example_rows().items()
    }


def generate(out_dir: Path) -> dict[str, Path]:
    """Write every fixture into ``out_dir``; returns name -> path."""
    files: dict[str, Path] = {}
    files.update({f"header:{c}": p for c, p in split_header_examples(out_dir).items()})
    return files


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    files = generate(out)
    print(f"{len(files)} fixtures written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
