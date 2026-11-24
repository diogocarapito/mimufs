"""Regenerate site/changelog.html and site/version.json from CHANGELOG.md.

Usage:
  python scripts/build_site.py            write both files
  python scripts/build_site.py --check    exit 1 if they are out of date (CI)
  python scripts/build_site.py --min-supported 0.1.0

``version.json`` is what the app's update check reads (TECH_SPECS §13). Its ``latest`` is the
newest dated section of CHANGELOG.md; the first bullets of that section become ``notes_pt``.
Stdlib only.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys

from changelog import ROOT, Release, load, plain

SITE = ROOT / "site"
DOWNLOAD_URL = "https://mimufs.com/#download"
MAX_NOTES = 5

_PAGE = """<!doctype html>
<html lang="pt-PT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'self'; style-src 'self'; img-src 'self'; script-src 'none'">
<meta name="referrer" content="no-referrer">
<title>Novidades · mimufs</title>
<meta name="description" content="Histórico de versões do mimufs.">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="top">
  <a class="brand" href="index.html"><img src="favicon.svg" alt="" width="22" height="22">mimufs</a>
  <nav><a href="index.html">Início</a><a href="sobre.html">Sobre</a>
  <a href="changelog.html" aria-current="page">Novidades</a></nav>
</header>
<main class="page">
<p class="kicker">MIMUFS · HISTÓRICO DE VERSÕES</p>
<h1>Novidades</h1>
<p class="lead">Gerado automaticamente a partir do <a href="https://github.com/diogocarapito/mimufs/blob/main/CHANGELOG.md">CHANGELOG.md</a>.</p>
{releases}
</main>
<footer class="foot"><p>mimufs · software livre (GPL-3.0) · <a href="https://github.com/diogocarapito/mimufs">código-fonte</a></p></footer>
</body>
</html>
"""

_CODE_RE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    return _CODE_RE.sub(r"<code>\1</code>", html.escape(text, quote=False))


def render_release(release: Release) -> str:
    parts = [
        f'<section class="release" id="v{html.escape(release.version)}">',
        f'<h2>{html.escape(release.version)} <span class="date">{release.date}</span></h2>',
    ]
    parts += [f"<p>{_inline(line)}</p>" for line in release.intro]
    for group, items in release.groups.items():
        parts.append(f"<h3>{html.escape(group)}</h3>")
        parts.append("<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ul>")
    parts.append("</section>")
    return "\n".join(parts)


def changelog_html(releases: list[Release]) -> str:
    body = (
        "\n".join(render_release(r) for r in releases) or "<p>Ainda não há versões publicadas.</p>"
    )
    return _PAGE.replace("{releases}", body)


def version_json(releases: list[Release], min_supported: str | None) -> str:
    if not releases:
        raise SystemExit("CHANGELOG.md has no dated release")
    latest = releases[0]
    doc = {
        "latest": latest.version,
        "released": latest.date,
        "min_supported": min_supported,
        "download_url": DOWNLOAD_URL,
        "notes_pt": [plain(item) for item in latest.bullets[:MAX_NOTES]],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def _current_min_supported() -> str | None:
    try:
        value = json.loads((SITE / "version.json").read_text(encoding="utf-8")).get("min_supported")
    except (OSError, ValueError):
        return None
    return value if isinstance(value, str) else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the files are stale")
    parser.add_argument("--min-supported", help="oldest version still supported")
    args = parser.parse_args(argv)
    releases = load()
    min_supported = args.min_supported or _current_min_supported()
    outputs = {
        SITE / "changelog.html": changelog_html(releases),
        SITE / "version.json": version_json(releases, min_supported),
    }
    stale = [p for p, text in outputs.items() if not p.exists() or p.read_text("utf-8") != text]
    if args.check:
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run python scripts/build_site.py")
        return 1 if stale else 0
    for path, text in outputs.items():
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print(f"site updated: latest {releases[0].version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
