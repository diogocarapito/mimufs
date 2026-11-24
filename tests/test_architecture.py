"""Architecture and privacy rules that are cheap to check statically (CLAUDE.md rules 1, 3)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from mimufs.core import db
from mimufs.core.readers import java_runtime

SRC = Path(__file__).resolve().parents[1] / "src" / "mimufs"
QT_MODULES = ("PySide6", "shiboken6", "PyQt5", "PyQt6", "qtpy")
NETWORK_MODULES = ("PySide6.QtNetwork", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
                   "requests", "httpx", "aiohttp", "urllib3")  # fmt: skip


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _python_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*.py") if "_runtime" not in p.parts)


def test_core_never_imports_qt() -> None:
    offenders = {
        path.relative_to(SRC).as_posix(): sorted(
            n for n in _imports(path) if n.startswith(QT_MODULES)
        )
        for path in _python_files(SRC / "core")
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_no_network_libraries_anywhere() -> None:
    offenders = {
        path.relative_to(SRC).as_posix(): sorted(
            n for n in _imports(path) if n.startswith(NETWORK_MODULES)
        )
        for path in _python_files(SRC)
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_urllib_only_in_the_update_module() -> None:
    users = {
        path.relative_to(SRC).as_posix()
        for path in _python_files(SRC)
        if any(n == "urllib.request" or n.startswith("urllib.request.") for n in _imports(path))
    }
    assert users == {"update.py"}


def test_duckdb_connections_have_extension_downloads_off(tmp_path: Path) -> None:
    con = db.connect(tmp_path / "t.mimufs")
    try:
        assert db.unsafe_settings(con) == {}
    finally:
        con.close()


def test_duckdb_only_connected_through_core_db() -> None:
    callers = {
        path.relative_to(SRC).as_posix()
        for path in _python_files(SRC)
        if "duckdb.connect(" in path.read_text(encoding="utf-8")
    }
    assert callers == {"core/db.py"}


def test_version_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mimufs", "--version"],
        capture_output=True, text=True, timeout=60, check=True,
    )  # fmt: skip
    from mimufs import __version__

    assert result.stdout.strip() == __version__


@pytest.mark.requires_java
@pytest.mark.skipif(java_runtime.find_java() is None, reason="no Java runtime on this machine")
def test_selftest_passes(tmp_path: Path) -> None:
    report = tmp_path / "selftest.txt"
    result = subprocess.run(
        [sys.executable, "-m", "mimufs", "--selftest", "--selftest-out", str(report)],
        capture_output=True, text=True, timeout=300,
        env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen"},
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    lines = report.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "selftest passed"
    assert {line.split(":")[0] for line in lines if line.startswith("ok ")} == {
        "ok   specs", "ok   duckdb", "ok   excel", "ok   java+tabula", "ok   netguard", "ok   qt",
    }  # fmt: skip
