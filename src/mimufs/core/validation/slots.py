"""Which extractions ("slots") a report needs, and which slots a file fills (TECH_SPECS §6.2).

Slot keys are stable strings stored with each imported file:

=================  ==============  =========================================
kind               key             tile label
=================  ==============  =========================================
months             ``2024-07``     ``Jul``
month_coverage     ``2024-T3``     ``T3`` (quarters) or ``Jul`` (months)
year               ``2024``        ``2024``
values             ``2024/hba1c``  spec label (``HbA1c``)
icpc_sets          ``2024/set2``   ``Lote 2``
=================  ==============  =========================================

Placing a file reads only its parsed metadata (filter, then Páginas), never its file name.
Problems found while placing (period outside the year, unknown exam…) are checks V04 and V06.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache

from mimufs.core.readers.mimuf_header import RawSheet, is_total
from mimufs.core.specs.loader import load_icpc_batches
from mimufs.core.specs.models import (
    IcpcBatches,
    IcpcSetsSlots,
    MimufReportSpec,
    MonthCoverageSlots,
    MonthsSlots,
    ValuesSlots,
    YearSlots,
)
from mimufs.core.validation import messages as M
from mimufs.core.validation.context import ProjectCtx
from mimufs.core.validation.result import Issue, Status

MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
QUARTER_RE = re.compile(r"^(\d{4})-T([1-4])$")
YEAR_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class SlotDef:
    key: str
    label: str
    year: int
    months: tuple[str, ...]  # YYYY-MM covered by this slot
    detail: str = ""  # e.g. "A01 → H99 · 205 códigos"


@dataclass(frozen=True)
class Placement:
    slot_keys: tuple[str, ...]  # slots the file fills (empty: none)
    months: tuple[str, ...]  # YYYY-MM the file covers (coverage reports, info card)
    period: str  # readable period, e.g. "2024-07", "2024-T3", "2024"
    issues: tuple[Issue, ...] = field(default_factory=tuple)


@cache
def icpc_batches(sets_file: str) -> IcpcBatches:
    return load_icpc_batches(sets_file)


def _ym(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def expected_slots(spec: MimufReportSpec, years: Sequence[int]) -> list[SlotDef]:
    """Every slot the report needs for the project's year(s), in display order."""
    slots = spec.slots
    many = len(years) > 1

    def lab(label: str, year: int) -> str:
        return f"{label} {year}" if many else label

    out: list[SlotDef] = []
    for y in years:
        if isinstance(slots, MonthsSlots):
            out += [
                SlotDef(_ym(y, m), lab(M.MONTHS_PT[m - 1], y), y, (_ym(y, m),))
                for m in slots.months
            ]
        elif isinstance(slots, MonthCoverageSlots):
            if slots.display == "quarters":
                for q in range(1, 5):
                    months = tuple(_ym(y, m) for m in range(3 * q - 2, 3 * q + 1))
                    out.append(SlotDef(f"{y}-T{q}", lab(f"T{q}", y), y, months))
            else:
                out += [
                    SlotDef(_ym(y, m), lab(M.MONTHS_PT[m - 1], y), y, (_ym(y, m),))
                    for m in slots.months
                ]
        elif isinstance(slots, YearSlots):
            out.append(SlotDef(str(y), str(y), y, tuple(_ym(y, m) for m in range(1, 13))))
        elif isinstance(slots, ValuesSlots):
            months = tuple(_ym(y, m) for m in slots.months)
            out += [
                SlotDef(f"{y}/{slot_id}", lab(slots.label(slot_id), y), y, months)
                for slot_id in slots.values
            ]
        elif isinstance(slots, IcpcSetsSlots):
            months = tuple(_ym(y, m) for m in slots.months)
            for b in icpc_batches(slots.sets_file).batches:
                detail = f"{b.first} → {b.last} · {b.unique} códigos"
                out.append(SlotDef(f"{y}/set{b.n}", lab(f"Lote {b.n}", y), y, months, detail))
    return out


# ------------------------------------------------------------------------------ periods


def file_months(raw: RawSheet) -> tuple[str, ...]:
    """Months (YYYY-MM) the file covers, from Mês or Trimestre (filter first, then pages)."""
    months: list[str] = []
    for value in raw.effective("mes"):
        if MONTH_RE.match(value.strip()):
            months.append(value.strip())
    for value in raw.effective("trimestre"):
        match = QUARTER_RE.match(value.strip())
        if match:
            y, q = int(match[1]), int(match[2])
            months += [_ym(y, m) for m in range(3 * q - 2, 3 * q + 1)]
    return tuple(sorted(set(months)))


def file_years(raw: RawSheet) -> tuple[int, ...]:
    years = {int(v) for v in raw.effective("ano") if YEAR_RE.match(v.strip())}
    if not years:
        years = {int(m[:4]) for m in file_months(raw)}
    return tuple(sorted(years))


def _period_text(raw: RawSheet, months: Sequence[str]) -> str:
    quarters = [v.strip() for v in raw.effective("trimestre") if QUARTER_RE.match(v.strip())]
    if quarters:
        return ", ".join(quarters)
    if not months:
        return ""
    if len(months) == 1:
        return months[0]
    return f"{months[0]} → {months[-1]}"


def _issue(template: str, severity: Status, location: str, **values: object) -> Issue:
    message, hint = M.text(template, **values)
    return Issue(template.split(".")[0], severity, message, location, hint)


# ---------------------------------------------------------------------------------- place


def place(raw: RawSheet, spec: MimufReportSpec, ctx: ProjectCtx, file_name: str) -> Placement:
    """The slot(s) a parsed file fills, plus V04/V06 issues found on the way."""
    slots = spec.slots
    loc = f"{file_name} · Filtro"
    years_text = ", ".join(str(y) for y in ctx.years)
    issues: list[Issue] = []

    if isinstance(slots, YearSlots):
        years = file_years(raw)
        if not years:
            issues.append(_issue("V04.no_period", Status.ERROR, loc, what="Ano"))
            return Placement((), (), "", tuple(issues))
        keys = []
        for y in years:
            if y in ctx.years:
                keys.append(str(y))
            else:
                issues.append(
                    _issue(
                        "V04.outside_year",
                        Status.ERROR,
                        loc,
                        period=y,
                        years=years_text,
                        what="Ano",
                        suggestion=ctx.years[0],
                    )
                )
        months = tuple(_ym(y, m) for y in years for m in range(1, 13))
        return Placement(tuple(keys), months, ", ".join(map(str, years)), tuple(issues))

    months = file_months(raw)
    period = _period_text(raw, months)
    what = "Mês ou Trimestre" if isinstance(slots, MonthCoverageSlots) else "Mês"
    if not months:
        issues.append(_issue("V04.no_period", Status.ERROR, loc, what=what))
        return Placement((), (), "", tuple(issues))

    expected_months = set(slots.months)
    expected_text = ", ".join(M.MONTHS_PT[m - 1] for m in sorted(expected_months))
    valid: list[str] = []
    for ym in months:
        y, m = int(ym[:4]), int(ym[5:])
        if y not in ctx.years:
            suggestion = _ym(ctx.years[0], min(expected_months))
            issues.append(
                _issue(
                    "V04.outside_year",
                    Status.ERROR,
                    loc,
                    period=ym,
                    years=years_text,
                    what="Mês",
                    suggestion=suggestion,
                )
            )
        elif m not in expected_months:
            suggestion = _ym(y, min(expected_months, key=lambda e: abs(e - m)))
            issues.append(
                _issue(
                    "V04.unexpected_month",
                    Status.WARNING,
                    loc,
                    period=ym,
                    expected=expected_text,
                    suggestion=suggestion,
                )
            )
        else:
            valid.append(ym)
    if not valid:
        return Placement((), months, period, tuple(issues))
    valid_years = sorted({int(v[:4]) for v in valid})

    if isinstance(slots, MonthsSlots):
        return Placement(tuple(valid), months, period, tuple(issues))
    if isinstance(slots, MonthCoverageSlots):
        if slots.display == "quarters":
            keys = sorted({f"{v[:4]}-T{(int(v[5:]) - 1) // 3 + 1}" for v in valid})
        else:
            keys = sorted(valid)
        return Placement(tuple(keys), months, period, tuple(issues))
    if isinstance(slots, ValuesSlots):
        return _place_value(raw, slots, valid_years, months, period, issues, loc)
    if isinstance(slots, IcpcSetsSlots):
        return _place_icpc(raw, slots, valid_years, months, period, issues, loc)
    raise TypeError(f"unknown slot kind for {spec.code}")


def _place_value(
    raw: RawSheet,
    slots: ValuesSlots,
    years: list[int],
    months: tuple[str, ...],
    period: str,
    issues: list[Issue],
    loc: str,
) -> Placement:
    key = slots.filter_key
    values = [v for c in raw.clauses(key) if c.op == "=" for v in c.values]
    if not values:
        page = raw.page(key)
        values = [page] if page and not is_total(page) else []
    if not values:
        issues.append(_issue("V06.slot_filter", Status.ERROR, loc, key=key))
        return Placement((), months, period, tuple(issues))
    keys: list[str] = []
    expected = ", ".join(slots.label(s) for s in slots.values)
    for value in values:
        matched = slots.match(value)
        if not matched:
            issues.append(
                _issue(
                    "V04.unknown_value",
                    Status.WARNING,
                    loc,
                    key=key,
                    value=value,
                    expected=expected,
                )
            )
            continue
        keys += [f"{y}/{matched[0]}" for y in years]
    return Placement(tuple(dict.fromkeys(keys)), months, period, tuple(issues))


def _place_icpc(
    raw: RawSheet,
    slots: IcpcSetsSlots,
    years: list[int],
    months: tuple[str, ...],
    period: str,
    issues: list[Issue],
    loc: str,
) -> Placement:
    codes = raw.icpc_codes()
    if not raw.clauses("ICPC"):
        issues.append(_issue("V06.slot_filter", Status.ERROR, loc, key="ICPC"))
        return Placement((), months, period, tuple(issues))
    best = max(
        icpc_batches(slots.sets_file).batches,
        key=lambda b: len(codes & set(b.codes)),
    )
    if not codes & set(best.codes):
        issues.append(_issue("V04.unknown_icpc_set", Status.WARNING, loc, n=len(codes)))
        return Placement((), months, period, tuple(issues))
    keys = tuple(f"{y}/set{best.n}" for y in years)
    return Placement(keys, months, period, tuple(issues))
