"""Validation result types (TECH_SPECS §7, PRD §6.1).

A status is ordered by how bad it is, so the status of anything made of parts is the worst
status among its parts (``max``): file → slot → report → step.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Status(IntEnum):
    PENDING = 0  # ⚪ not started (nothing imported)
    SKIPPED = 1  # ⚪ dashed: optional report the user skipped
    VALID = 2  # 🟢
    WARNING = 3  # 🟠 usable after explicit acknowledgement
    ERROR = 4  # 🔴 must be fixed (or the file removed)


@dataclass(frozen=True)
class Issue:
    """One problem: what is wrong (message), where (location) and how to fix it (fix_hint)."""

    check_id: str  # "V05", "S01"
    severity: Status  # WARNING or ERROR
    message: str  # PT-PT
    location: str | None = None  # "ficheiro.xls · Páginas"
    fix_hint: str | None = None  # PT-PT, actionable
    file_id: int | None = None  # the stored file it belongs to (None: report-level)

    def __post_init__(self) -> None:
        if self.severity not in (Status.WARNING, Status.ERROR):
            raise ValueError("an issue is a warning or an error")


def worst(statuses: Iterable[Status], default: Status = Status.VALID) -> Status:
    return max(statuses, default=default)


def status_of(issues: Iterable[Issue]) -> Status:
    return worst((i.severity for i in issues), Status.VALID)


@dataclass
class ValidationResult:
    status: Status
    issues: list[Issue]
    info: dict[str, Any] = field(default_factory=dict)
