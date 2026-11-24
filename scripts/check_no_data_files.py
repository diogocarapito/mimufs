"""Fail if a data file (possible patient data) is tracked or staged in git.

Usage:  python scripts/check_no_data_files.py
Run by the pre-commit hook (.githooks/pre-commit) and by CI. Stdlib only, so it runs with
any Python. CLAUDE.md rule 2: no real patient data in the repo, ever. Synthetic fixtures are
generated into tests/fixtures/generated/, which is git-ignored.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys

BLOCKED_SUFFIXES = (
    ".xls", ".xlsx", ".xlsm", ".xlsb", ".ods",
    ".csv", ".tsv", ".parquet", ".pdf",
    ".mimufs", ".duckdb", ".db", ".sqlite",
)  # fmt: skip

# Files that are allowed although their suffix is blocked. Keep this list short and reviewed.
ALLOWED = (
    "docs/reference/MIMUF_Header_examples.xlsx",  # real headers only, anonymised, no rows
    "src/mimufs/core/reference/dictionaries/*.csv",  # bundled reference dictionaries
)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached"], check=True, capture_output=True
    ).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def offending(paths: list[str]) -> list[str]:
    bad = []
    for path in paths:
        if not path.lower().endswith(BLOCKED_SUFFIXES):
            continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in ALLOWED):
            continue
        bad.append(path)
    return bad


def main() -> int:
    bad = offending(tracked_files())
    if bad:
        print("Data files must not be committed (possible patient data):", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        print(
            "Synthetic fixtures belong in tests/fixtures/generated/ (git-ignored). "
            "If this file is safe, add it to ALLOWED in scripts/check_no_data_files.py.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
