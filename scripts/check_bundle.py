"""Fail if a built bundle contains network-capable Qt parts (TECH_SPECS §12.3), and report its size.

Usage:  python scripts/check_bundle.py build/
Run by the release workflow after `briefcase build` on every OS. Stdlib only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Path parts that must never ship: Qt's network stack and web engine (CLAUDE.md rule 1).
FORBIDDEN = re.compile(
    r"""(
        Qt6?Network | QtNetwork | libQt6Network
      | Qt6?WebEngine | QtWebEngine | QtWebView | QtWebSockets
      | /plugins/tls/ | /plugins/networkinformation/
      | qopensslbackend | qschannelbackend | qsecuretransportbackend | qcertonlybackend
      | /pyarrow/_?(s3fs|gcsfs|azurefs|hdfs)
      | /pyarrow/libarrow_s3
    )""",
    re.VERBOSE | re.IGNORECASE,
)


def offending(root: Path) -> list[str]:
    return sorted(
        rel
        for path in root.rglob("*")
        if FORBIDDEN.search(rel := "/" + path.relative_to(root).as_posix())
    )


def size_mb(root: Path) -> float:
    total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    return total / 1_000_000


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    root = Path(argv[0])
    bad = offending(root)
    print(f"{root}: {size_mb(root):.0f} MB")
    if bad:
        print("forbidden network-capable files in the bundle:")
        print("\n".join(f"  {p}" for p in bad[:50]))
        return 1
    print("no QtNetwork/WebEngine/TLS parts found")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
