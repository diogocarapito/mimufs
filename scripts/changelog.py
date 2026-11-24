"""Parse CHANGELOG.md (Keep a Changelog, PT-PT entries). Shared by the site and release scripts.

Stdlib only: the release workflow runs these scripts before any dependency is installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"

_RELEASE_RE = re.compile(
    r"^## \[(?P<version>\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.]+)?)\] - (?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
_SECTION_RE = re.compile(r"^## ")
_GROUP_RE = re.compile(r"^### (?P<name>.+?)\s*$")
_BULLET_RE = re.compile(r"^- (?P<text>.+?)\s*$")


@dataclass
class Release:
    version: str
    date: str
    intro: list[str] = field(default_factory=list)
    groups: dict[str, list[str]] = field(default_factory=dict)

    @property
    def bullets(self) -> list[str]:
        return [item for items in self.groups.values() for item in items]


def parse(text: str) -> list[Release]:
    """Dated releases, newest first (the order of the file). ``[Não publicado]`` is skipped."""
    releases: list[Release] = []
    current: Release | None = None
    group: str | None = None
    for line in text.splitlines():
        match = _RELEASE_RE.match(line)
        if match:
            current = Release(match["version"], match["date"])
            releases.append(current)
            group = None
            continue
        if _SECTION_RE.match(line):
            current = None  # e.g. "## [Não publicado]"
            continue
        if current is None:
            continue
        if group_match := _GROUP_RE.match(line):
            group = group_match["name"]
            current.groups.setdefault(group, [])
        elif bullet := _BULLET_RE.match(line):
            current.groups.setdefault(group or "Alterações", []).append(bullet["text"])
        elif line.strip() and group is None:
            current.intro.append(line.strip())
    return releases


def load(path: Path = CHANGELOG) -> list[Release]:
    return parse(path.read_text(encoding="utf-8"))


def find(version: str, releases: list[Release]) -> Release | None:
    return next((r for r in releases if r.version == version), None)


def plain(text: str) -> str:
    """Markdown inline code/emphasis stripped (for the app's dialog and version.json)."""
    return re.sub(r"[`*_]", "", text)
