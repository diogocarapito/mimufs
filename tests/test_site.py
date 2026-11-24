"""mimufs.com (site/) and the release scripts (TECH_SPECS §16.3, §17; PRD §8)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from mimufs.update import VersionDoc, evaluate

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = sorted(SITE.glob("*.html"))
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

sys.path.insert(0, str(ROOT / "scripts"))
import changelog  # noqa: E402


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=60
    )


def test_version_json_is_what_the_app_expects() -> None:
    doc = VersionDoc.model_validate(json.loads((SITE / "version.json").read_text("utf-8")))
    assert doc.latest == VERSION
    assert evaluate(doc, VERSION, None) is None  # the current build sees no update
    newer = evaluate(doc, "0.0.0", None)
    assert newer is not None
    assert newer.notes_pt


def test_generated_files_are_up_to_date() -> None:
    result = _run("scripts/build_site.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_release_notes_for_the_current_version() -> None:
    result = _run("scripts/release_notes.py", f"v{VERSION}", "--check-pyproject")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "mimufs-windows-x64-portable.zip" in result.stdout
    assert _run("scripts/release_notes.py", "9.9.9").returncode != 0


def test_changelog_parser() -> None:
    releases = changelog.parse(
        "# Changelog\n\n## [Não publicado]\n\n- ainda não\n\n"
        "## [0.2.0] - 2027-01-15\n\nIntro.\n\n### Adicionado\n\n- Novo `P05.01.L02`\n"
        "### Corrigido\n\n- Trimestres\n\n## [0.1.0] - 2026-12-20\n\n- Primeira\n"
    )
    assert [(r.version, r.date) for r in releases] == [
        ("0.2.0", "2027-01-15"),
        ("0.1.0", "2026-12-20"),
    ]
    assert releases[0].intro == ["Intro."]
    assert releases[0].groups == {"Adicionado": ["Novo `P05.01.L02`"], "Corrigido": ["Trimestres"]}
    assert releases[1].bullets == ["Primeira"]
    assert changelog.plain("Novo `P05.01.L02`") == "Novo P05.01.L02"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_load_nothing_from_other_sites(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    # Stylesheets, scripts, images, fonts, frames: local only. Plain links (<a>) may point out.
    for tag in re.findall(r"<(?:link|script|img|iframe|source|video|audio)\b[^>]*>", text):
        assert "http" not in tag, tag
        assert "//" not in tag, tag
    assert "@import" not in (SITE / "style.css").read_text(encoding="utf-8")
    assert "url(" not in (SITE / "style.css").read_text(encoding="utf-8")
    assert 'lang="pt-PT"' in text
    assert "Content-Security-Policy" in text


def test_inline_script_matches_its_csp_hash() -> None:
    text = (SITE / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", text, re.S)
    assert len(scripts) == 1
    digest = base64.b64encode(hashlib.sha256(scripts[0].encode("utf-8")).digest()).decode()
    assert f"'sha256-{digest}'" in text


def test_download_links_use_the_stable_artefact_names() -> None:
    text = (SITE / "index.html").read_text(encoding="utf-8")
    links = set(re.findall(r"releases/latest/download/([\w.-]+)", text))
    assert links == {
        "mimufs-windows-x64-portable.zip",
        "mimufs-windows-x64.msi",
        "mimufs-macos-arm64.dmg",
        "mimufs-macos-x64.dmg",
        "mimufs-linux-x86_64.deb",
        "mimufs-linux-x86_64.flatpak",
    }


def test_domain_and_favicon() -> None:
    assert (SITE / "CNAME").read_text(encoding="utf-8").strip() == "mimufs.com"
    assert (SITE / "favicon.svg").read_bytes() == (ROOT / "packaging/icons/mimufs.svg").read_bytes()


def test_privacy_page_states_the_exact_update_request() -> None:
    text = (SITE / "sobre.html").read_text(encoding="utf-8")
    assert "GET https://mimufs.com/version.json" in text
    assert "User-Agent: mimufs/&lt;versão&gt;" in text
