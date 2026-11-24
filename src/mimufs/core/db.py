"""DuckDB connections for project files (TECH_SPECS §4.1).

Every connection is opened through :func:`connect`, which turns off extension auto-install and
auto-load: DuckDB would otherwise download extensions (e.g. ``httpfs``) from the internet the
first time a query needs one, from C++ code that :mod:`mimufs.netguard` cannot see.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import duckdb

#: Settings that must hold on every connection (checked by tests and ``--selftest``).
SAFE_SETTINGS: Final[dict[str, bool]] = {
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "allow_community_extensions": False,
}


def default_threads() -> int:
    return max(2, (os.cpu_count() or 2) - 1)


def connect(path: Path | str, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open (or create) a project database with the safe configuration."""
    config: dict[str, str | bool | int | float | list[str]] = {
        **SAFE_SETTINGS,
        "threads": default_threads(),
    }
    return duckdb.connect(str(path), read_only=read_only, config=config)


def unsafe_settings(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    """Safe settings that do not hold on ``con`` (empty when all is well)."""
    wrong: dict[str, object] = {}
    for name, expected in SAFE_SETTINGS.items():
        # fetchall(): DuckDB 2.0 refuses new work while an execute() result is unfinished.
        rows = con.execute("SELECT current_setting(?)", [name]).fetchall()
        value = rows[0][0] if rows else None
        if value != expected:
            wrong[name] = value
    return wrong
