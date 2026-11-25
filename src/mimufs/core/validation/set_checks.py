"""Report-level checks over all files of one report: V11 and S01–S04 (PRD §6.3.2).

Run again whenever a file of the report is added or removed. Issues about one file (V11) carry
its ``file_id``; the others belong to the report.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from mimufs.core.readers.mimuf_header import RawSheet
from mimufs.core.specs.models import IcpcSetsSlots, MimufReportSpec, MonthCoverageSlots
from mimufs.core.validation import messages as M
from mimufs.core.validation.context import ProjectCtx, norm_text
from mimufs.core.validation.result import Issue, Status
from mimufs.core.validation.slots import Placement, SlotDef, expected_slots, icpc_batches


@dataclass(frozen=True)
class ReportFile:
    """What the report-level checks need about one imported file."""

    file_id: int
    name: str
    sha256: str
    raw: RawSheet
    placement: Placement


def _issue(
    template: str,
    severity: Status,
    location: str | None = None,
    file_id: int | None = None,
    **values: object,
) -> Issue:
    message, hint = M.text(template, **values)
    return Issue(template.split(".")[0], severity, message, location, hint, file_id)


def check_duplicates(
    files: Sequence[ReportFile], slot_labels: dict[str, str], *, coverage: bool = False
) -> tuple[list[Issue], set[int]]:
    """V11: identical files, or two files for the same slot. Returns (issues, duplicate ids)."""
    issues: list[Issue] = []
    first_by_sha: dict[str, ReportFile] = {}
    first_by_slot: dict[str, ReportFile] = {}
    duplicates: set[int] = set()
    for f in sorted(files, key=lambda f: f.file_id):
        if f.sha256 in first_by_sha:
            duplicates.add(f.file_id)
            issues.append(
                _issue(
                    "V11.same_file",
                    Status.WARNING,
                    f.name,
                    f.file_id,
                    other=first_by_sha[f.sha256].name,
                )
            )
            continue
        first_by_sha[f.sha256] = f
        if coverage:
            continue  # overlapping periods of coverage reports are S01's job
        for key in f.placement.slot_keys:
            if key in first_by_slot:
                issues.append(
                    _issue(
                        "V11.same_slot",
                        Status.WARNING,
                        f.name,
                        f.file_id,
                        slot=slot_labels.get(key, key),
                        other=first_by_slot[key].name,
                    )
                )
            else:
                first_by_slot[key] = f
    return issues, duplicates


def check_completeness(
    spec: MimufReportSpec, files: Sequence[ReportFile], slots: Sequence[SlotDef]
) -> list[Issue]:
    """S01: every required slot filled; coverage reports cover the 12 months without overlap."""
    if isinstance(spec.slots, IcpcSetsSlots):
        return []  # S02 reports missing ICPC sets with their code ranges
    if isinstance(spec.slots, MonthCoverageSlots):
        expected = [m for s in slots for m in s.months]
        counts = Counter(m for f in files for m in set(f.placement.months))
        issues = []
        missing = [m for m in expected if not counts[m]]
        if missing:
            issues.append(
                _issue(
                    "S01.missing_months",
                    Status.WARNING,
                    items=M.listing(M.month_label(m) for m in missing),
                )
            )
        overlap = sorted(m for m, n in counts.items() if n > 1 and m in expected)
        if overlap:
            issues.append(
                _issue(
                    "S01.overlap",
                    Status.WARNING,
                    items=M.listing(M.month_label(m) for m in overlap),
                )
            )
        return issues
    filled = {k for f in files for k in f.placement.slot_keys}
    missing_slots = [s for s in slots if s.key not in filled]
    if not missing_slots:
        return []
    n = len(missing_slots)
    return [
        _issue(
            "S01.missing_slots",
            Status.WARNING,
            n=n,
            plural_s=M.plural(n, "", "m"),
            plural_oes=M.plural(n, "ão", "ões"),
            items=M.listing(s.label for s in missing_slots),
        )
    ]


def check_icpc_coverage(spec: MimufReportSpec, files: Sequence[ReportFile]) -> list[Issue]:
    """S02: the ICPC codes in all batch filters cover the target list."""
    if not isinstance(spec.slots, IcpcSetsSlots):
        return []
    batches = icpc_batches(spec.slots.sets_file)
    per_file = [f.raw.icpc_codes() for f in files]
    covered: set[str] = set().union(*per_file) if per_file else set()
    issues: list[Issue] = []
    missing = batches.target - covered
    for b in batches.batches:
        if not covered & set(b.codes):
            issues.append(
                _issue(
                    "S02.missing_set",
                    Status.WARNING,
                    n=b.n,
                    first=b.first,
                    last=b.last,
                    count=b.unique,
                )
            )
            missing -= set(b.codes)
    if missing:
        issues.append(
            _issue("S02.missing", Status.WARNING, n=len(missing), items=M.listing(sorted(missing)))
        )
    counts = Counter(code for codes in per_file for code in codes)
    overlap = sorted(c for c, n in counts.items() if n > 1)
    if overlap:
        issues.append(
            _issue("S02.overlap", Status.WARNING, n=len(overlap), items=M.listing(overlap))
        )
    return issues


def check_consistency(spec: MimufReportSpec, files: Sequence[ReportFile]) -> list[Issue]:
    """S03: same unit and flags in every file of the report."""
    if len(files) < 2:
        return []
    issues: list[Issue] = []
    fields: dict[str, dict[str, str]] = {"a unidade": {}}
    for f in files:
        for value in f.raw.effective("unidade"):
            fields["a unidade"].setdefault(norm_text(value), value)
        for key in spec.pages_expect:
            page = f.raw.page(key)
            if page is not None:
                fields.setdefault(f"«{key}»", {}).setdefault(norm_text(page), page)
    for what, values in fields.items():
        if len(values) > 1:
            issues.append(
                _issue(
                    "S03.inconsistent",
                    Status.ERROR,
                    what=what,
                    items=M.listing(sorted(values.values())),
                )
            )
    return issues


def check_structure(files: Sequence[ReportFile]) -> list[Issue]:
    """S04: identical column structure across the files of the report."""
    groups: dict[tuple[tuple[str, ...], tuple[str, ...] | None], list[str]] = defaultdict(list)
    for f in sorted(files, key=lambda f: f.file_id):
        groups[(f.raw.header, f.raw.header2)].append(f.name)
    if len(groups) < 2:
        return []
    odd = [name for names in list(groups.values())[1:] for name in names]
    return [_issue("S04.columns", Status.ERROR, items=M.listing(odd))]


def check_report(
    spec: MimufReportSpec, files: Sequence[ReportFile], project: ProjectCtx
) -> list[Issue]:
    """Every report-level check. No files → no issues (the report is simply pending)."""
    if not files:
        return []
    slots = expected_slots(spec, project.years)
    coverage = isinstance(spec.slots, MonthCoverageSlots)
    issues, duplicates = check_duplicates(files, {s.key: s.label for s in slots}, coverage=coverage)
    distinct = [f for f in files if f.file_id not in duplicates]
    issues += check_completeness(spec, distinct, slots)
    issues += check_icpc_coverage(spec, distinct)
    issues += check_consistency(spec, distinct)
    issues += check_structure(distinct)
    return issues
