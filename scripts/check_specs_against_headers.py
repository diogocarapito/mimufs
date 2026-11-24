"""Check every report spec against the real MIM@UF headers.

Usage:  uv run python scripts/check_specs_against_headers.py
Exit code 1 if any spec column does not match the header cell at its position, or if the
file has a titled header cell that the spec does not describe. Meant to become a pytest test
(tests/core/test_specs_match_headers.py) in M0/M1.
"""
import html
import pathlib
import re
import sys

import openpyxl
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
XLSX = ROOT / "docs/reference/MIMUF_Header_examples.xlsx"
SPECS = ROOT / "src/mimufs/core/specs/reports"


def norm(value) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or "")).strip())


def header_rows(rows):
    """First row with >= 2 non-empty cells after the last metadata marker."""
    meta_end = 0
    for i, row in enumerate(rows):
        if row and norm(row[0]) in ("Páginas:", "Filtro do relatório:"):
            meta_end = i
    return next(i for i in range(meta_end + 1, len(rows)) if sum(1 for c in rows[i] if norm(c)) >= 2)


def main() -> int:
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    problems = 0
    for path in sorted(SPECS.glob("P*.yaml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        rows = [list(r) for r in wb[spec["code"]].iter_rows(values_only=True)]
        hi = header_rows(rows)
        row1, row2 = rows[hi], (rows[hi + 1] if spec["header"]["rows"] == 2 else None)
        described = set()
        for c in spec["header"]["columns"]:
            described.add(c["at"])
            got = norm((row2 if c.get("row2") else row1)[c["at"]]) if c["at"] < len(row1) else ""
            want = c["header"]
            if not (got == want or (c.get("match") == "startswith" and got.startswith(want))):
                problems += 1
                print(f"MISMATCH {spec['code']} col {c['at']}: file={got!r} spec={want!r}")
        extra = [(i, norm(v)) for i, v in enumerate(row1) if norm(v) and i not in described]
        if extra:
            problems += 1
            print(f"UNDESCRIBED {spec['code']}: {extra}")
        print(f"ok  {spec['code']:<15} header row {hi + 1}, {len(spec['header']['columns'])} columns")
    print("problems:", problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
