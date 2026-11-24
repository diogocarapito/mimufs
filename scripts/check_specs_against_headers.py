"""Check every report spec against the real MIM@UF headers.

Usage:  uv run python scripts/check_specs_against_headers.py
Exit code 1 if any spec column does not match the header cell at its position, or if the file
has a titled header cell that the spec does not describe.

A thin CLI over the real parser (mimufs.core.readers.mimuf_header). The same check runs in
pytest: tests/core/test_mimuf_header.py::test_real_header_parses_and_binds.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mimufs.core.readers.mimuf_header import bind_columns, read_mimuf_file  # noqa: E402
from mimufs.core.specs import mimuf_specs  # noqa: E402
from tests.fixtures.make_fixtures import split_header_examples  # noqa: E402


def main() -> int:
    problems = 0
    specs = mimuf_specs()
    with tempfile.TemporaryDirectory() as tmp:
        files = split_header_examples(Path(tmp))
        for code, spec in specs.items():
            if code not in files:
                problems += 1
                print(f"MISSING  {code}: no sheet in the header workbook")
                continue
            raw = read_mimuf_file(files[code], specs)
            if raw.code != code:
                problems += 1
                print(f"CODE     {code}: parser identified {raw.code!r}")
                continue
            bound = bind_columns(raw, spec)
            for m in bound.mismatches:
                problems += 1
                print(f"MISMATCH {code} col {m.at}: file={m.found!r} spec={m.expected!r}")
            if bound.extra_columns:
                problems += 1
                print(f"UNDESCRIBED {code}: {list(bound.extra_columns)}")
            n = len(spec.header.columns)
            print(f"ok  {code:<15} via {raw.code_source:<16} {n} columns")
    print("problems:", problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
