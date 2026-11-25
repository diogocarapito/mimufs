"""Print the GitHub Release notes of one version, from CHANGELOG.md.

Usage:  python scripts/release_notes.py 0.0.1 [--check-pyproject]
Exits 1 when the version has no dated section (the release workflow then stops), or, with
``--check-pyproject``, when it differs from ``[project].version`` in pyproject.toml.
"""

from __future__ import annotations

import argparse
import sys
import tomllib

from changelog import ROOT, find, load

DOWNLOADS = (
    ("Windows (portátil, sem instalação)", "mimufs-windows-x64-portable.zip"),
    ("Windows (instalador, sem administrador)", "mimufs-windows-x64.msi"),
    ("macOS — Apple Silicon (M1 ou mais recente)", "mimufs-macos-arm64.dmg"),
    ("macOS — Intel", "mimufs-macos-x64.dmg"),
)


def notes(version: str) -> str:
    release = find(version, load())
    if release is None:
        raise SystemExit(f"CHANGELOG.md has no dated section for {version}")
    lines = [*release.intro, ""] if release.intro else []
    for group, items in release.groups.items():
        lines += [f"### {group}", "", *(f"- {item}" for item in items), ""]
    lines += ["### Transferências", ""]
    lines += [f"- {label}: `{artefact}`" for label, artefact in DOWNLOADS]
    lines += ["", "Instruções de instalação: https://mimufs.com/#instalar"]
    return "\n".join(lines).strip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--check-pyproject", action="store_true")
    args = parser.parse_args(argv)
    version = args.version.removeprefix("v")
    if args.check_pyproject:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        if project["project"]["version"] != version:
            print(f"pyproject.toml version is {project['project']['version']}, tag is {version}")
            return 1
    sys.stdout.write(notes(version))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
