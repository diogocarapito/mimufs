"""Offline end-to-end run of everything built so far (TECH_SPECS §12.3).

The pipeline runs in a fresh subprocess with :mod:`mimufs.netguard` installed (it cannot be
uninstalled, so never in the pytest process) while pytest-socket blocks sockets here. It must
make **zero** network attempts. On Linux, CI also runs this file inside ``unshare --net``, which
cuts off every process, the Java subprocess included.

M0 scope: synthetic fixtures → parse + bind every MIM@UF file → SClínico CSV (+ PDF through
tabula when Java is available) → the bundle selftest. Each milestone extends it (project,
import, aggregate, quality, export).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROBE = r"""
import json, sys
from mimufs import netguard
netguard.install()

from pathlib import Path
from mimufs.core.readers import java_runtime, sclinico_pdf, tabula_runner
from mimufs.core.readers.excel import UnreadableFileError
from mimufs.core.readers.mimuf_header import bind_columns, read_mimuf_file
from tests.fixtures import make_fixtures

out = Path(sys.argv[1])
fixtures = make_fixtures.generate(out)
summary = {"mimuf_files": 0, "mimuf_rows": 0, "errors": [], "pdf_rows": None}
for name, fx in sorted(fixtures.items()):
    if fx.kind == "not_excel":
        try:
            read_mimuf_file(fx.path)
            summary["errors"].append(f"{name}: read as Excel")
        except UnreadableFileError:
            pass
    elif fx.kind == "sclinico_csv":
        frame = sclinico_pdf.read_appointments(fx.path)
        if frame.height != fx.n_rows:
            summary["errors"].append(f"{name}: {frame.height} rows")
    elif fx.kind == "sclinico_pdf":
        if java_runtime.find_java() is not None:
            tables = tabula_runner.read_pdf_tables(fx.path, lattice=True)
            summary["pdf_rows"] = sum(len(t) for t in tables)
    else:
        raw = read_mimuf_file(fx.path)
        if raw.code != fx.code or raw.spec is None:
            summary["errors"].append(f"{name}: identified as {raw.code}")
            continue
        bound = bind_columns(raw, raw.spec)
        if not bound.ok or raw.n_rows != fx.n_rows:
            summary["errors"].append(f"{name}: bind/rows mismatch")
        summary["mimuf_files"] += 1
        summary["mimuf_rows"] += raw.n_rows
summary["expected_pdf_rows"] = fixtures["sclinico/pdf"].n_rows
before = netguard.stats()
summary["blocked_before_selftest"] = before.blocked
summary["allowed"] = before.allowed

from mimufs import selftest
has_java = summary["pdf_rows"] is not None
checks = tuple(c for c in selftest.CHECKS if c[0] != "java+tabula" or has_java)
summary["selftest"] = selftest.run(out / "selftest.txt", checks)
summary["blocked_total"] = netguard.stats().blocked
print("SUMMARY " + json.dumps(summary))
"""


def test_pipeline_runs_offline(tmp_path: Path) -> None:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    line = next((ln for ln in result.stdout.splitlines() if ln.startswith("SUMMARY ")), None)
    assert line is not None, result.stdout + result.stderr
    summary = json.loads(line.removeprefix("SUMMARY "))

    assert summary["errors"] == []
    assert summary["mimuf_files"] >= 17 + 44  # header examples + one valid file per slot
    assert summary["mimuf_rows"] > 0
    if summary["pdf_rows"] is not None:
        assert summary["pdf_rows"] == summary["expected_pdf_rows"]
    # Not a single network attempt by the pipeline; the update check never ran.
    assert summary["blocked_before_selftest"] == 0
    assert summary["allowed"] == 0
    assert summary["selftest"] == 0, (tmp_path / "selftest.txt").read_text(encoding="utf-8")
    # The selftest's own probe is the only blocked attempt (it proves the guard is active).
    assert summary["blocked_total"] == 1
