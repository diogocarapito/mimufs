"""File-level checks V03–V10 (PRD §6.3.2) on a parsed, spec-bound MIM@UF export.

V01 (readable) and V02 (recognised report) happen at import, before there is a parsed sheet;
V04 (period/slot) and the slot part of V06 happen while placing the file (``slots.place``);
V11 (duplicates) needs the other files of the report (``set_checks``); V12 (footer) is not an
issue: the footer is removed and reported in the info card.

Each check is a pure function ``FileCtx -> list[Issue]`` registered in ``FILE_CHECKS``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from mimufs.core.readers.excel import ROW_CEILING
from mimufs.core.readers.mimuf_header import (
    BoundSheet,
    RawSheet,
    bind_columns,
    is_total,
    key_alias,
)
from mimufs.core.specs.models import MimufReportSpec
from mimufs.core.validation import messages as M
from mimufs.core.validation.context import ProjectCtx, norm_text
from mimufs.core.validation.result import Issue, Status
from mimufs.core.validation.slots import Placement, place

SNS_RE = re.compile(r"^\d{9}$")


@dataclass(frozen=True)
class FileCtx:
    raw: RawSheet
    spec: MimufReportSpec
    bound: BoundSheet
    project: ProjectCtx
    name: str  # file name, for locations
    file_id: int | None = None


def column_letter(index: int) -> str:
    """0 → A, 25 → Z, 26 → AA (Excel column names)."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _issue(ctx: FileCtx, template: str, severity: Status, where: str, **values: object) -> Issue:
    message, hint = M.text(template, **values)
    location = f"{ctx.name} · {where}" if where else ctx.name
    return Issue(template.split(".")[0], severity, message, location, hint, ctx.file_id)


def _values(raw: RawSheet, key: str) -> tuple[list[str], str]:
    """Values of a field and where they came from: filter ("=") first, then Páginas."""
    filtered = [v for c in raw.clauses(key) if c.op == "=" for v in c.values]
    if filtered:
        return filtered, "Filtro"
    page = raw.page(key)
    if page is not None:
        return [page], "Páginas"
    return [], ""


# --------------------------------------------------------------------------------- checks


def check_unit(ctx: FileCtx) -> list[Issue]:
    """V03: the unit is the project's unit (filter first; Páginas can say Total)."""
    raw = ctx.raw
    unit_cols = ctx.spec.header.by_role("unit")
    column_values: list[str] = []
    if unit_cols and unit_cols[0].name in ctx.bound.data.columns:
        column_values = ctx.bound.data[unit_cols[0].name].drop_nulls().unique().to_list()
    found = raw.effective("unidade", column_values)
    page = raw.page("unidade")
    if any(c.op == "=" for c in raw.clauses("unidade")):
        where = "Filtro"
    elif page is not None and not is_total(page):
        where = "Páginas"
    else:
        where = f"coluna {column_letter(unit_cols[0].at)}" if unit_cols else ""
    if not found:
        return [_issue(ctx, "V03.missing", Status.WARNING, "", expected=ctx.project.unit)]
    return [
        _issue(ctx, "V03.mismatch", Status.ERROR, where, found=value, expected=ctx.project.unit)
        for value in found
        if not ctx.project.same_unit(value)
    ]


def check_filter_vs_pages(ctx: FileCtx) -> list[Issue]:
    """V05: filter and Páginas agree. ``Total`` in Páginas is never a conflict."""
    issues: list[Issue] = []
    for key, page_value in ctx.raw.pages.items():
        if is_total(page_value):
            continue
        alias = key_alias(key)
        for clause in ctx.raw.filter:
            if clause.op != "=":
                continue
            same = norm_text(clause.key) == norm_text(key) or (alias and clause.alias == alias)
            if same and norm_text(page_value) not in {norm_text(v) for v in clause.values}:
                issues.append(
                    _issue(
                        ctx,
                        "V05.conflict",
                        Status.WARNING,
                        "Filtro e Páginas",
                        key=key,
                        filter_value=clause.value,
                        page_value=page_value,
                    )
                )
    return issues


def check_required_values(ctx: FileCtx) -> list[Issue]:
    """V06: the filter/page values the report needs, and the doctor pages rule."""
    raw, spec, project = ctx.raw, ctx.spec, ctx.project
    issues: list[Issue] = []
    expectations = [(k, {v}) for k, v in spec.pages_expect.items()]
    for key, value in spec.filter_expect.items():
        allowed = {value.replace("{ano}", str(y)) for y in project.years}
        expectations.append((key, allowed))
    for key, allowed in expectations:
        found, where = _values(raw, key)
        shown = " ou ".join(sorted(allowed))
        if not found:
            issues.append(_issue(ctx, "V06.missing", Status.WARNING, "", key=key, expected=shown))
            continue
        wanted = {norm_text(a) for a in allowed}
        for value in found:
            if norm_text(value) not in wanted:
                issues.append(
                    _issue(
                        ctx,
                        "V06.value",
                        Status.WARNING,
                        where,
                        key=key,
                        expected=shown,
                        found=value,
                    )
                )
    for key in spec.doctor_pages:
        found, where = _values(raw, key)
        for value in found:
            if is_total(value) or project.is_project_doctor(value):
                continue
            issues.append(
                _issue(ctx, "V06.other_doctor", Status.ERROR, where, key=key, found=value)
            )
    return issues


def check_columns(ctx: FileCtx) -> list[Issue]:
    """V07: the spec's columns at their positions; unknown titled columns are a warning."""
    issues: list[Issue] = []
    for m in ctx.bound.mismatches:
        position = column_letter(m.at)
        where = "Cabeçalho"
        if m.found is None:
            issues.append(
                _issue(
                    ctx, "V07.missing", Status.ERROR, where, expected=m.expected, position=position
                )
            )
        elif m.found == "":
            issues.append(
                _issue(
                    ctx, "V07.blank", Status.ERROR, where, expected=m.expected, position=position
                )
            )
        else:
            issues.append(
                _issue(
                    ctx,
                    "V07.mismatch",
                    Status.ERROR,
                    where,
                    expected=m.expected,
                    found=m.found,
                    position=position,
                )
            )
    issues += [
        _issue(
            ctx, "V07.extra", Status.WARNING, "Cabeçalho", found=found, position=column_letter(at)
        )
        for at, found in ctx.bound.extra_columns
    ]
    return issues


def check_rows(ctx: FileCtx) -> list[Issue]:
    """V08: at least one data row."""
    return [] if ctx.raw.n_rows else [_issue(ctx, "V08.empty", Status.WARNING, "")]


def check_truncation(ctx: FileCtx) -> list[Issue]:
    """V09: a sheet at the format's row ceiling was almost certainly cut."""
    ceiling = ROW_CEILING.get(ctx.raw.format)
    if ceiling is None or ctx.raw.max_row < ceiling:
        return []
    return [
        _issue(
            ctx, "V09.truncated", Status.ERROR, "", rows=f"{ctx.raw.max_row:,}".replace(",", " ")
        )
    ]


def id_counts(bound: BoundSheet) -> tuple[int, int]:
    """(rows using the NOP fallback, rows with no usable ID). (0, 0) without an SNS column."""
    sns_cols = bound.spec.header.by_role("sns")
    if not sns_cols or sns_cols[0].name not in bound.data.columns:
        return 0, 0
    sns = pl.col(sns_cols[0].name).fill_null("").str.strip_chars()
    bad = ~sns.str.contains(r"^\d{9}$")
    nop_cols = bound.spec.header.by_role("nop")
    if nop_cols and nop_cols[0].name in bound.data.columns:
        has_nop = pl.col(nop_cols[0].name).fill_null("").str.strip_chars() != ""
    else:
        has_nop = pl.lit(False)
    counts = bound.data.select(
        (bad & has_nop).sum().alias("nop"), (bad & ~has_nop).sum().alias("none")
    ).row(0)
    return int(counts[0] or 0), int(counts[1] or 0)


def check_ids(ctx: FileCtx) -> list[Issue]:
    """V10: patients identified by a 9-digit SNS number (NOP is the fallback)."""
    n_nop, n_none = id_counts(ctx.bound)
    if not (n_nop or n_none):
        return []
    parts = []
    if n_nop:
        parts.append(
            f"{n_nop} {M.plural(n_nop, 'linha', 'linhas')} sem número de utente SNS válido "
            f"{M.plural(n_nop, 'usa', 'usam')} o NOP"
        )
    if n_none:
        verb = M.plural(n_none, "linha não tem", "linhas não têm")
        parts.append(f"{n_none} {verb} identificação do utente")
    summary = "; ".join(parts) + "."
    summary = summary[0].upper() + summary[1:]
    sns_col = ctx.spec.header.by_role("sns")[0]
    return [
        _issue(
            ctx, "V10.ids", Status.WARNING, f"coluna {column_letter(sns_col.at)}", summary=summary
        )
    ]


FILE_CHECKS: dict[str, Callable[[FileCtx], list[Issue]]] = {
    "V03": check_unit,
    "V05": check_filter_vs_pages,
    "V06": check_required_values,
    "V07": check_columns,
    "V08": check_rows,
    "V09": check_truncation,
    "V10": check_ids,
}


@dataclass(frozen=True)
class FileCheckResult:
    placement: Placement
    issues: tuple[Issue, ...]
    bound: BoundSheet


def check_file(
    raw: RawSheet,
    spec: MimufReportSpec,
    project: ProjectCtx,
    name: str,
    file_id: int | None = None,
) -> FileCheckResult:
    """Place the file in its slot(s) and run every file-level check."""
    bound = bind_columns(raw, spec)
    ctx = FileCtx(raw, spec, bound, project, name, file_id)
    placement = place(raw, spec, project, name)
    placed = [
        Issue(i.check_id, i.severity, i.message, i.location, i.fix_hint, file_id)
        for i in placement.issues
    ]
    issues = placed + [issue for check in FILE_CHECKS.values() for issue in check(ctx)]
    return FileCheckResult(placement, tuple(issues), bound)
