"""MIM@UF export parser: metadata block, filter, Páginas, header and data (TECH_SPECS §5.2).

A MIM@UF export looks like this (real samples in ``docs/reference/mimuf_header_samples.md``)::

    P01.01.L01. Inscritos &gt; Utente                  ← code + title (HTML-escaped)
    Filtro do relatório:
    (Mês = 2024-01) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)
    Páginas:                                          ← optional section
    Mês: 2024-01                                      ← "Key: Value" or "Key = Value"
    NOP | Utente | (blank) | Sexo | …                 ← header, 1 or 2 rows
    …data…
    Total | | … | 23149                               ← optional footer (check V12)

Auto-detection of the report uses only this parsed content, never the file name.
"""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import polars as pl

from mimufs.core.readers.excel import FileFormat, SheetRows, read_first_sheet
from mimufs.core.specs.models import Column, MimufReportSpec

TITLE_RE = re.compile(r"^(P\d{2}(?:\.\d{2}){0,2}\.[LR]\d{2})\.\s*(.+)$")
FILTER_MARKER = "Filtro do relatório:"
PAGES_MARKER = "Páginas:"
OPERATORS = ("<>", ">=", "<=", "=", ">", "<")
_OP_RE = "|".join(re.escape(op) for op in OPERATORS)
_BRACED_CLAUSE_RE = re.compile(
    rf"^\{{(?P<key>[^}}]*)\}}(?P<suffix>\s*\([^)]*\))?\s*(?P<op>{_OP_RE})\s*(?P<value>.*)$", re.S
)
_BARE_CLAUSE_RE = re.compile(rf"^(?P<key>[^<>={{}}]+?)\s*(?P<op>{_OP_RE})\s*(?P<value>.*)$", re.S)
_PAGE_LINE_RE = re.compile(r"^(?P<key>[^:=]+?)\s*[:=]\s*(?P<value>.*)$", re.S)

# List values are split only where the next token clearly starts a new item.
_ICPC_ITEM_RE = re.compile(r"^[A-Z]\d{2}(?=:|,|\s*$)")
_ICPC_SPLIT_RE = re.compile(r",\s*(?=[A-Z]\d{2}(?::|,|$))")
_PERIOD_LIST_RE = re.compile(r"^\d{4}-(?:\d{2}|T[1-4])(?:\s*,\s*\d{4}-(?:\d{2}|T[1-4]))+$")
_PERIOD_SPLIT_RE = re.compile(r",\s*(?=\d{4}-(?:\d{2}|T[1-4])\b)")
ICPC_CODE_RE = re.compile(r"^([A-Z]\d{2})(?::|$)")

#: Page/filter keys normalised before checks (TECH_SPECS §5.2 step 4).
KEY_ALIASES: dict[str, str] = {
    "unidade funcional / polo hospitalar": "unidade",
    "unidade funcional": "unidade",
    "mês": "mes",
    "trimestre": "trimestre",
    "ano": "ano",
}

TOTAL = "total"


class HeaderParseError(ValueError):
    """The metadata block or the table header cannot be found (check V01/V02)."""


def norm(value: str) -> str:
    """Unescape HTML entities and collapse whitespace (metadata and header cells)."""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def key_alias(key: str) -> str | None:
    return KEY_ALIASES.get(norm(key).casefold())


def is_total(value: str | None) -> bool:
    return value is not None and norm(value).casefold() == TOTAL


# ------------------------------------------------------------------------------- filter


@dataclass(frozen=True, slots=True)
class Clause:
    """One ``key op value`` clause of the report filter."""

    key: str  # braces stripped, suffix kept: "Tipo Risco (ID)"
    op: str
    value: str  # whole value text
    values: tuple[str, ...]  # list items (one item when the value is not a list)
    raw: str

    @property
    def alias(self) -> str | None:
        return key_alias(self.key)


class FilterParseError(ValueError):
    pass


def parse_filter(text: str) -> tuple[Clause, ...]:
    """Parse a MIM@UF filter expression into clauses (a small tokenizer, not a regex split)."""
    text = norm(text)
    if not text:
        return ()
    return tuple(parse_clause(part) for part in split_clauses(text) if part.strip())


def split_clauses(text: str) -> list[str]:
    """Split on top-level `` E `` while tracking parenthesis depth.

    Values can contain parentheses (``A79:CARCINOMATOSE (LOCALIZAÇÃO …)``); if they are ever
    unbalanced, fall back to splitting only at ``) E (`` / ``) E {`` boundaries.
    """
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    balanced = True
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                balanced = False
                break
        elif depth == 0 and text.startswith(" E ", i):
            parts.append(text[start:i])
            i += 3
            start = i
            continue
        i += 1
    if balanced and depth == 0:
        parts.append(text[start:])
        return [p.strip() for p in parts]
    return [p.strip() for p in re.split(r"(?<=\))\s+E\s+(?=[({])", text)]


def _matching_paren(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_clause(raw: str) -> Clause:
    s = raw.strip()
    if s.startswith("(") and s.endswith(")"):
        balanced = s.count("(") == s.count(")")
        if not balanced or _matching_paren(s, 0) == len(s) - 1:
            s = s[1:-1].strip()
    match = _BRACED_CLAUSE_RE.match(s) or _BARE_CLAUSE_RE.match(s)
    if not match:
        raise FilterParseError(f"cannot parse filter clause: {raw[:80]!r}")
    key = match["key"].strip()
    suffix = match.groupdict().get("suffix")
    if suffix:
        key = f"{key} {suffix.strip()}"
    value = match["value"].strip()
    return Clause(key=key, op=match["op"], value=value, values=split_values(value), raw=raw)


def split_values(value: str) -> tuple[str, ...]:
    """Split a list value only where a new item clearly starts; otherwise keep it whole."""
    if _ICPC_ITEM_RE.match(value):
        return tuple(v.strip() for v in _ICPC_SPLIT_RE.split(value) if v.strip())
    if _PERIOD_LIST_RE.match(value):
        return tuple(v.strip() for v in _PERIOD_SPLIT_RE.split(value) if v.strip())
    return (value,)


def parse_page_line(text: str) -> tuple[str, str] | None:
    """``Key: Value`` or ``Key = Value``, split on the first separator only."""
    match = _PAGE_LINE_RE.match(norm(text))
    if not match:
        return None
    return match["key"].strip(), match["value"].strip()


# ------------------------------------------------------------------------------ metadata


@dataclass(frozen=True, slots=True)
class Metadata:
    title_raw: str
    code: str | None  # from the title cell; None when the cell is damaged
    title: str
    filter_text: str
    filter: tuple[Clause, ...]
    pages: dict[str, str]
    has_pages: bool
    header_row: int  # 0-based index of the first header row


def _first_text(row: Sequence[str]) -> str:
    return next((c for c in row if c and c.strip()), "")


def _non_empty(row: Sequence[str]) -> int:
    return sum(1 for c in row if c and c.strip())


def parse_metadata(rows: Sequence[Sequence[str]]) -> Metadata:
    title_idx = next((i for i, r in enumerate(rows) if _non_empty(r)), None)
    if title_idx is None:
        raise HeaderParseError("empty sheet")
    title_raw = _first_text(rows[title_idx])
    title_norm = norm(title_raw)
    match = TITLE_RE.match(title_norm)
    code, title = (match[1], match[2].strip()) if match else (None, _strip_code_prefix(title_norm))

    filter_idx = next(
        (i for i, r in enumerate(rows) if norm(_first_text(r)) == FILTER_MARKER), None
    )
    if filter_idx is None:
        raise HeaderParseError("no 'Filtro do relatório:' marker")
    filter_text_idx = next(
        (i for i in range(filter_idx + 1, len(rows)) if _non_empty(rows[i])), None
    )
    if filter_text_idx is None:
        raise HeaderParseError("no filter after the marker")
    filter_text = norm(_first_text(rows[filter_text_idx]))
    meta_end = filter_text_idx

    pages: dict[str, str] = {}
    pages_idx = next(
        (
            i
            for i in range(filter_text_idx + 1, len(rows))
            if norm(_first_text(rows[i])) == PAGES_MARKER
        ),
        None,
    )
    # Páginas belongs to the metadata only if it comes before the header row.
    first_table_row = next(
        (i for i in range(filter_text_idx + 1, len(rows)) if _non_empty(rows[i]) >= 2), None
    )
    has_pages = pages_idx is not None and (first_table_row is None or pages_idx < first_table_row)
    if has_pages and pages_idx is not None:
        meta_end = pages_idx
        for i in range(pages_idx + 1, len(rows)):
            if not _non_empty(rows[i]) or _non_empty(rows[i]) >= 2:
                break
            parsed = parse_page_line(_first_text(rows[i]))
            if parsed:
                pages[parsed[0]] = parsed[1]
            meta_end = i

    header_row = next((i for i in range(meta_end + 1, len(rows)) if _non_empty(rows[i]) >= 2), None)
    if header_row is None:
        raise HeaderParseError("no header row after the metadata")
    return Metadata(
        title_raw=title_raw,
        code=code,
        title=title,
        filter_text=filter_text,
        filter=parse_filter(filter_text),
        pages=pages,
        has_pages=has_pages,
        header_row=header_row,
    )


def _strip_code_prefix(title: str) -> str:
    """Drop a damaged code prefix such as ``1.01.L03.`` from the title text."""
    return re.sub(r"^[\w.]*\d[\w.]*\.\s+", "", title)


# --------------------------------------------------------------------------- report sheet

CodeSource = Literal["title", "title_text", "header_signature", "unknown"]


@dataclass(frozen=True)
class RawSheet:
    """A parsed export: metadata + positional raw table (TECH_SPECS §5.2 step 7).

    ``rows`` has one Utf8 column per source position (``c0``, ``c1``, …; ``drop: true`` columns
    of the spec already removed) plus ``_row``, the 1-based row number in the sheet. Blank cells
    are null. Footer rows are removed (they remain in the byte copy in ``raw/``).
    """

    code: str | None
    code_source: CodeSource
    title: str
    title_raw: str
    filter_text: str
    filter: tuple[Clause, ...]
    pages: dict[str, str]
    has_pages: bool
    header: tuple[str, ...]
    header2: tuple[str, ...] | None
    rows: pl.DataFrame
    footer_rows: tuple[tuple[str, ...], ...]
    max_row: int
    format: FileFormat
    sheet_name: str
    source_sha256: str = ""
    spec: MimufReportSpec | None = field(default=None, repr=False)

    @property
    def n_rows(self) -> int:
        return self.rows.height

    def clauses(self, key_or_alias: str) -> tuple[Clause, ...]:
        wanted = key_or_alias.casefold()
        return tuple(
            c for c in self.filter if c.key.casefold() == wanted or (c.alias or "") == wanted
        )

    def page(self, key_or_alias: str) -> str | None:
        wanted = key_or_alias.casefold()
        for key, value in self.pages.items():
            if key.casefold() == wanted or (key_alias(key) or "") == wanted:
                return value
        return None

    def effective(self, key_or_alias: str, column_values: Sequence[str] = ()) -> tuple[str, ...]:
        """Effective value(s) of a field: filter, else page (unless ``Total``), else column.

        ``Total`` in Páginas never conflicts with a filter restriction (TECH_SPECS §5.2).
        ``column_values`` is the fallback for the unit (distinct values of a role-unit column).
        """
        for clause in self.clauses(key_or_alias):
            if clause.op == "=":
                return clause.values
        page = self.page(key_or_alias)
        if page is not None and not is_total(page):
            return (page,)
        return tuple(dict.fromkeys(v for v in column_values if v))

    def icpc_codes(self) -> frozenset[str]:
        """ICPC codes listed in the filter (P04.01.L01 batches)."""
        codes: set[str] = set()
        for clause in self.clauses("ICPC"):
            for item in clause.values:
                match = ICPC_CODE_RE.match(item.strip())
                if match:
                    codes.add(match[1])
        return frozenset(codes)


def read_mimuf_file(path: Path, specs: Mapping[str, MimufReportSpec] | None = None) -> RawSheet:
    """Read and parse one MIM@UF export from disk."""
    sheet = read_first_sheet(path)
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return parse_sheet(sheet, specs, source_sha256=sha256)


def parse_sheet(
    sheet: SheetRows,
    specs: Mapping[str, MimufReportSpec] | None = None,
    *,
    source_sha256: str = "",
) -> RawSheet:
    if specs is None:
        from mimufs.core.specs.loader import mimuf_specs

        specs = mimuf_specs()
    rows = sheet.rows
    meta = parse_metadata(rows)
    header1 = tuple(norm(c) for c in rows[meta.header_row])
    code, code_source, spec = _identify(meta, header1, rows, specs)

    n_header = spec.header.rows if spec else 1
    header2 = (
        tuple(norm(c) for c in rows[meta.header_row + 1])
        if n_header == 2 and meta.header_row + 1 < len(rows)
        else None
    )
    first_data = meta.header_row + n_header
    end = next((i for i in range(first_data, len(rows)) if not _non_empty(rows[i])), len(rows))
    data = list(rows[first_data:end])
    row_numbers = list(range(first_data + 1, end + 1))

    footer: list[tuple[str, ...]] = []
    while data and _is_footer(data[-1], spec):
        footer.insert(0, tuple(data.pop()))
        row_numbers.pop()

    width = max(len(header1), sheet.width)
    dropped = {c.at for c in spec.header.columns if c.drop} if spec else set()
    columns: dict[str, list[str | None]] = {
        f"c{i}": [(r[i] if i < len(r) and r[i] != "" else None) for r in data]
        for i in range(width)
        if i not in dropped
    }
    frame = pl.DataFrame(
        {**columns, "_row": row_numbers},
        schema={**dict.fromkeys(columns, pl.Utf8), "_row": pl.UInt32},
    )
    return RawSheet(
        code=code,
        code_source=code_source,
        title=meta.title,
        title_raw=meta.title_raw,
        filter_text=meta.filter_text,
        filter=meta.filter,
        pages=meta.pages,
        has_pages=meta.has_pages,
        header=header1,
        header2=header2,
        rows=frame,
        footer_rows=tuple(footer),
        max_row=sheet.max_row,
        format=sheet.format,
        sheet_name=sheet.sheet_name,
        source_sha256=source_sha256,
        spec=spec,
    )


def _identify(
    meta: Metadata,
    header1: tuple[str, ...],
    rows: Sequence[Sequence[str]],
    specs: Mapping[str, MimufReportSpec],
) -> tuple[str | None, CodeSource, MimufReportSpec | None]:
    """Report code from the title; if the cell is damaged, title text + header signature."""
    if meta.code is not None:
        return meta.code, "title", specs.get(meta.code)

    def signature_ok(spec: MimufReportSpec) -> bool:
        h2 = (
            tuple(norm(c) for c in rows[meta.header_row + 1])
            if spec.header.rows == 2 and meta.header_row + 1 < len(rows)
            else ()
        )
        return all(
            _cell_at(h2 if col.row2 else header1, col.at) is not None
            and col.matches(_cell_at(h2 if col.row2 else header1, col.at) or "")
            for col in spec.header.columns
            if col.header
        )

    by_title = [s for s in specs.values() if norm(s.title) == meta.title]
    matches = [s for s in by_title if signature_ok(s)]
    if len(matches) == 1:
        return matches[0].code, "title_text", matches[0]
    matches = [s for s in specs.values() if signature_ok(s)]
    if len(matches) == 1:
        return matches[0].code, "header_signature", matches[0]
    return None, "unknown", None


def _cell_at(row: Sequence[str], at: int) -> str | None:
    return row[at] if at < len(row) else None


def _is_footer(row: Sequence[str], spec: MimufReportSpec | None) -> bool:
    """``Total`` in the first cell and the ID (or, without IDs, dimension) columns empty."""
    if not row or not is_total(row[0]):
        return False

    def empty(at: int) -> bool:
        return at >= len(row) or not row[at].strip()

    if spec is None:
        # Without a spec: everything between the first cell and the trailing numbers is empty.
        cells = [c.strip() for c in row[1:]]
        while cells and _looks_numeric(cells[-1]):
            cells.pop()
        return not any(cells)
    ids = [c.at for c in spec.id_columns if c.at != 0]
    if ids:
        return all(empty(at) for at in ids)
    dims = [c.at for c in spec.header.columns if c.at != 0 and c.type in ("str", "cat", "date")]
    return all(empty(at) for at in dims)


def _looks_numeric(text: str) -> bool:
    return bool(re.fullmatch(r"-?[\d.,\s]+", text)) if text else True


# ---------------------------------------------------------------------- binding to a spec


@dataclass(frozen=True, slots=True)
class ColumnMismatch:
    at: int
    name: str
    expected: str
    found: str | None  # None = the column is missing
    required: bool


@dataclass(frozen=True)
class BoundSheet:
    """A raw sheet with its columns named by the spec (input to checks and staging)."""

    raw: RawSheet
    spec: MimufReportSpec
    data: pl.DataFrame  # canonical names; ignore/drop columns removed; plus ``_row``
    mismatches: tuple[ColumnMismatch, ...]
    extra_columns: tuple[tuple[int, str], ...]  # titled cells the spec does not describe
    untitled_named: tuple[tuple[int, str], ...]  # (position, spec name) for blank header cells

    @property
    def ok(self) -> bool:
        return not self.mismatches and not self.extra_columns


def bind_columns(raw: RawSheet, spec: MimufReportSpec) -> BoundSheet:
    """Name the positional columns after the spec (check V07 uses the mismatches)."""
    mismatches: list[ColumnMismatch] = []
    rename: dict[str, str] = {}
    untitled: list[tuple[int, str]] = []
    for col in spec.header.columns:
        row = raw.header2 if col.row2 and raw.header2 is not None else raw.header
        found = _cell_at(row, col.at)
        if found is None or not col.matches(found):
            mismatches.append(_mismatch(col, found))
            continue
        if col.header == "":
            untitled.append((col.at, col.name))
        if col.type != "ignore" and not col.drop:
            rename[f"c{col.at}"] = col.name
    described = {c.at for c in spec.header.columns}
    extra = tuple((i, cell) for i, cell in enumerate(raw.header) if cell and i not in described)
    keep = [c for c in rename if c in raw.rows.columns]
    data = raw.rows.select([pl.col(c).alias(rename[c]) for c in keep] + [pl.col("_row")])
    return BoundSheet(
        raw=raw,
        spec=spec,
        data=data,
        mismatches=tuple(mismatches),
        extra_columns=extra,
        untitled_named=tuple(untitled),
    )


def _mismatch(col: Column, found: str | None) -> ColumnMismatch:
    return ColumnMismatch(
        at=col.at, name=col.name, expected=col.header, found=found, required=col.required
    )
