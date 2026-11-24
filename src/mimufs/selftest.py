"""``mimufs --selftest``: prove that a built bundle works, without any user data or display.

Run by CI on every release bundle (TECH_SPECS §16.3) and useful on a user's PC when something
fails. Each check uses synthetic data only and prints one line; the exit code is 0 only when
every check passes. Checks: report specs, DuckDB (safe config, Arrow/Polars round-trip), the
Excel reader and MIM@UF parser, the bundled Java + tabula, the network guard and Qt.
"""

from __future__ import annotations

import datetime as dt
import os
import socket
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from mimufs import __version__, netguard

SELFTEST_ROWS: list[list[object]] = [
    ["P01.01.L01. Inscritos &gt; Utente"],
    [],
    ["Filtro do relatório:"],
    ["(Mês = 2024-12) E ({Unidade Funcional / Polo Hospitalar} = USF Teste)"],
    [],
    ["Páginas:"],
    ["Mês: 2024-12"],
    ["Flag Médico Família: C/ Med Fam"],
    [],
    ["NOP", "Utente", None, "Sexo", "Idade", "Data Nascimento", "Médico Familia",
     "Freguesia Habitação"],
    [4000001, 900000001, "Utente 0001", "F", 40, dt.date(1984, 1, 1), "MEDICO: M 00001", "Teste"],
    [4000002, 900000002, "Utente 0002", "M", 50, dt.date(1974, 1, 1), "MEDICO: M 00001", "Teste"],
]  # fmt: skip


def check_specs(_tmp: Path) -> str:
    from mimufs.core.specs import load_specs
    from mimufs.core.specs.loader import load_icpc_batches

    specs = load_specs()
    target = load_icpc_batches().target
    return f"{len(specs)} specs, {len(target)} ICPC codes"


def check_duckdb(tmp: Path) -> str:
    import duckdb
    import polars as pl

    from mimufs.core import db

    con = db.connect(tmp / "selftest.mimufs")
    try:
        wrong = db.unsafe_settings(con)
        if wrong:
            raise RuntimeError(f"unsafe DuckDB settings: {wrong}")
        frame = con.sql("SELECT 42 AS answer").pl()
        if not isinstance(frame, pl.DataFrame) or frame["answer"].to_list() != [42]:
            raise RuntimeError("Arrow/Polars round-trip failed")
    finally:
        con.close()
    return f"duckdb {duckdb.__version__}, polars {pl.__version__}"


def check_excel(tmp: Path) -> str:
    import openpyxl

    from mimufs.core.readers.mimuf_header import bind_columns, read_mimuf_file

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in SELFTEST_ROWS:
        ws.append(row)
    path = tmp / "selftest.xls"  # OOXML with an .xls name, like MIM@UF
    with path.open("wb") as fh:
        wb.save(fh)
    raw = read_mimuf_file(path)
    if raw.code != "P01.01.L01" or raw.spec is None or raw.n_rows != 2:
        raise RuntimeError(f"parsed {raw.code!r} with {raw.n_rows} rows")
    if not bind_columns(raw, raw.spec).ok:
        raise RuntimeError("columns do not match the spec")
    return f"openpyxl {openpyxl.__version__}"


def check_java(tmp: Path) -> str:
    from mimufs.core.readers import java_runtime, tabula_runner
    from mimufs.selftest_pdf import make_table_pdf

    runtime = java_runtime.configure()
    header = ["Data", "Utente", "Profissional"]
    rows = [[f"2024-01-{d:02d}", f"9000000{d:02d}", "Médico Teste"] for d in range(1, 13)]
    pdf = tmp / "selftest.pdf"
    pdf.write_bytes(make_table_pdf(header, rows, rows_per_page=8))
    tables = tabula_runner.read_pdf_tables(pdf, lattice=True, pandas_options={"dtype": str})
    n = sum(len(t) for t in tables)
    if n != len(rows):
        raise RuntimeError(f"tabula read {n} rows, expected {len(rows)}")
    kind = "bundled JRE" if runtime.bundled else "system Java"
    return f"{kind}: {runtime.version}"


def check_netguard(_tmp: Path) -> str:
    if not netguard.is_installed():
        raise RuntimeError("network guard is not installed")
    try:
        socket.getaddrinfo("example.invalid", 443)
    except netguard.NetworkBlockedError:
        return "DNS lookup blocked"
    raise RuntimeError("a DNS lookup was not blocked")


def check_qt(tmp: Path) -> str:
    headless = sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    if headless:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import importlib.util

    from PySide6 import __version__ as pyside_version

    from mimufs.gui.app import create_application
    from mimufs.gui.main_window import MainWindow
    from mimufs.settings import SettingsStore

    app = create_application([sys.argv[0] if sys.argv else "mimufs"])
    window = MainWindow(SettingsStore(tmp / "settings.json"))  # never the user's settings
    window.show()
    app.processEvents()
    window.close()
    app.processEvents()
    qtnetwork = "absent" if importlib.util.find_spec("PySide6.QtNetwork") is None else "present"
    return f"PySide6 {pyside_version} on {app.platformName()}, QtNetwork {qtnetwork}"


CHECKS: tuple[tuple[str, Callable[[Path], str]], ...] = (
    ("specs", check_specs),
    ("duckdb", check_duckdb),
    ("excel", check_excel),
    ("java+tabula", check_java),
    ("netguard", check_netguard),
    ("qt", check_qt),
)


def _write(line: str, report: list[str]) -> None:
    report.append(line)
    if sys.stdout is not None:  # None in a Windows GUI build
        print(line, flush=True)


def run(
    out_path: Path | None = None, checks: tuple[tuple[str, Callable[[Path], str]], ...] = CHECKS
) -> int:
    report: list[str] = []
    _write(
        f"mimufs {__version__} selftest ({sys.platform}, Python {sys.version.split()[0]})", report
    )
    failures = 0
    with tempfile.TemporaryDirectory(prefix="mimufs-selftest-") as tmp:
        for name, check in checks:
            start = time.perf_counter()
            try:
                detail = check(Path(tmp))
            except Exception as exc:
                failures += 1
                _write(f"FAIL {name}: {type(exc).__name__}: {exc}", report)
            else:
                _write(f"ok   {name}: {detail} [{time.perf_counter() - start:.1f}s]", report)
    _write("selftest passed" if not failures else f"selftest FAILED ({failures})", report)
    if out_path is not None:
        out_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0 if not failures else 1
