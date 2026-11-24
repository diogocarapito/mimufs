"""A tiny dependency-free PDF writer for table-shaped test documents.

Used by the bundle's ``--selftest`` (to prove the bundled JRE + tabula-java work) and by the
synthetic fixture generator (SClínico-style appointment lists). Text only, Helvetica,
WinAnsi encoding; optional ruling lines so both tabula modes (stream/lattice) can be tried.
"""

from __future__ import annotations

from collections.abc import Sequence

PAGE_W, PAGE_H = 842, 595  # A4 landscape, points
MARGIN = 40
ROW_H = 18
FONT_SIZE = 9


def _escape(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _page_stream(
    title: str,
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    col_x: Sequence[float],
    ruled: bool,
) -> bytes:
    ops: list[bytes] = []
    y = PAGE_H - MARGIN
    ops.append(b"BT /F1 12 Tf %d %d Td (%s) Tj ET" % (MARGIN, y, _escape(title)))
    y -= 2 * ROW_H
    table_top = y + ROW_H - 4
    for i, line in enumerate([header, *rows]):
        font = b"/F2" if i == 0 else b"/F1"
        for x, cell in zip(col_x, line, strict=False):
            ops.append(
                b"BT %s %d Tf %.1f %d Td (%s) Tj ET" % (font, FONT_SIZE, x + 3, y, _escape(cell))
            )
        y -= ROW_H
    if ruled:
        bottom = y + ROW_H - 4
        right = PAGE_W - MARGIN
        ops.append(b"0.5 w")
        for k in range(len(rows) + 2):
            yy = table_top - k * ROW_H
            ops.append(b"%d %.1f m %d %.1f l S" % (MARGIN, yy, right, yy))
        for x in [*col_x, right]:
            ops.append(b"%.1f %.1f m %.1f %.1f l S" % (x, table_top, x, bottom))
    return b"\n".join(ops)


def make_table_pdf(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    title: str = "Lista de consultas realizadas",
    rows_per_page: int = 25,
    ruled: bool = True,
    widths: Sequence[float] | None = None,
) -> bytes:
    """A PDF whose pages each repeat the title and header row above a slice of ``rows``."""
    usable = PAGE_W - 2 * MARGIN
    widths = list(widths) if widths else [usable / len(header)] * len(header)
    scale = usable / sum(widths)
    col_x: list[float] = []
    x = float(MARGIN)
    for w in widths:
        col_x.append(x)
        x += w * scale

    chunks = [rows[i : i + rows_per_page] for i in range(0, len(rows), rows_per_page)] or [[]]
    objects: list[bytes] = []  # object n is objects[n - 1]

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    catalog = add(b"")  # placeholder, filled below
    pages = add(b"")
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>"
    font1 = add(font % b"Helvetica")
    font2 = add(font % b"Helvetica-Bold")
    kids: list[int] = []
    for n, chunk in enumerate(chunks, start=1):
        stream = _page_stream(f"{title} - pagina {n}/{len(chunks)}", header, chunk, col_x, ruled)
        content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        kids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> >>"
                % (pages, PAGE_W, PAGE_H, content, font1, font2)
            )
        )
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages
    objects[pages - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, obj)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        catalog,
        xref,
    )
    return bytes(out)
