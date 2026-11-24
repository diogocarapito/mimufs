"""Render the app icon (mimufs.svg) into every format Briefcase and the GUI need.

Usage:  uv run python packaging/icons/make_icons.py
Writes, next to this script:
  mimufs.icns                   macOS (PNG-based ICNS, 16-1024 px)
  mimufs.ico                    Windows (PNG-based ICO, 16-256 px)
  mimufs-{16..512}.png          Linux system packages and Flatpak
and src/mimufs/gui/icons/app.png (256 px window icon). Run again after changing the SVG.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SVG = HERE / "mimufs.svg"
LINUX_SIZES = (16, 32, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# ICNS PNG element types (Apple Icon Image format).
ICNS_TYPES = {
    b"icp4": 16, b"icp5": 32, b"ic11": 32, b"icp6": 64, b"ic12": 64, b"ic07": 128,
    b"ic08": 256, b"ic13": 256, b"ic09": 512, b"ic14": 512, b"ic10": 1024,
}  # fmt: skip


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data.data())


def write_ico(path: Path, pngs: dict[int, bytes]) -> None:
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, png in sorted(pngs.items()):
        dim = 0 if size >= 256 else size  # 0 means 256 in ICO
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    path.write_bytes(header + entries + blobs)


def write_icns(path: Path, pngs: dict[int, bytes]) -> None:
    body = b"".join(
        kind + struct.pack(">I", 8 + len(pngs[size])) + pngs[size]
        for kind, size in ICNS_TYPES.items()
    )
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)


def main() -> int:
    app = QGuiApplication([sys.argv[0], "-platform", "offscreen"])
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        raise SystemExit(f"invalid SVG: {SVG}")
    sizes = sorted({*LINUX_SIZES, *ICO_SIZES, *ICNS_TYPES.values()})
    pngs = {size: render_png(renderer, size) for size in sizes}
    for size in LINUX_SIZES:
        (HERE / f"mimufs-{size}.png").write_bytes(pngs[size])
    write_ico(HERE / "mimufs.ico", {s: pngs[s] for s in ICO_SIZES})
    write_icns(HERE / "mimufs.icns", pngs)
    (ROOT / "src" / "mimufs" / "gui" / "icons" / "app.png").write_bytes(pngs[256])
    del app
    print(f"icons written to {HERE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
