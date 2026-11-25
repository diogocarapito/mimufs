"""The report info card ("Metadados", PRD §6.3.3): one card per report, merged across its files.

Values are counts and metadata only (unit, period, filters, files, rows, columns), never patient
values, so the card can be copied as a methods summary ("copiar resumo").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mimufs.core.project import Project, ReportState
from mimufs.core.readers.mimuf_header import BoundSheet, RawSheet, bind_columns, is_total
from mimufs.core.specs.loader import load_icpc_batches
from mimufs.core.specs.models import IcpcSetsSlots, MimufReportSpec, ValuesSlots
from mimufs.core.validation import messages as M
from mimufs.core.validation.checks import id_counts
from mimufs.core.validation.result import Status

STATUS_PT = {
    Status.PENDING: "Por importar",
    Status.SKIPPED: "Dispensado",
    Status.VALID: "Válido",
    Status.WARNING: "Incompleto",
    Status.ERROR: "Erro",
}
LEVEL_PT = {
    "patient": "utente",
    "patient_event": "utente (eventos)",
    "doctor": "médico",
    "unit": "unidade",
    "family": "família",
}


def number(n: int) -> str:
    """PT-PT thousands separator (thin space): 23 149."""
    return f"{n:,}".replace(",", " ")


@dataclass(frozen=True)
class InfoCard:
    code: str
    title: str
    subtitle: str  # "MIM@UF · nível utente"
    rows: tuple[tuple[str, str], ...]  # (label, value)

    def markdown(self) -> str:
        lines = [f"### {self.code} · {self.title}", "", f"*{self.subtitle}*", ""]
        lines += [f"- **{label}**: {value}" for label, value in self.rows]
        return "\n".join(lines) + "\n"


def _period(months: Sequence[str], expected: Sequence[str]) -> str:
    if not months:
        return "—"
    text = months[0] if len(months) == 1 else f"{months[0]} → {months[-1]}"
    gaps = [m for m in expected if m not in set(months)]
    if gaps and len(expected) > 1:
        text += f" (sem dados: {M.listing(M.month_label(g) for g in gaps)})"
    return text


def build_card(project: Project, state: ReportState) -> InfoCard:
    spec = state.spec
    level = LEVEL_PT.get(spec.level, spec.level)
    source = "MIM@UF" if isinstance(spec, MimufReportSpec) else "SClínico"
    subtitle = f"{source} · nível {level}"
    rows: list[tuple[str, str]] = [("Estado", _status_text(state))]
    if not state.files or not isinstance(spec, MimufReportSpec):
        rows.append(("Ficheiros", "0"))
        return InfoCard(spec.code, spec.title, subtitle, tuple(rows))

    sheets: list[RawSheet] = [project.load_sheet(f.file_id) for f in state.files]
    bounds = [bind_columns(raw, spec) for raw in sheets]

    units: dict[str, str] = {}
    for raw, bound in zip(sheets, bounds, strict=True):
        unit_cols = spec.header.by_role("unit")
        column_values: list[str] = []
        if unit_cols and unit_cols[0].name in bound.data.columns:
            column_values = bound.data[unit_cols[0].name].drop_nulls().unique().to_list()
        for value in raw.effective("unidade", column_values):
            units.setdefault(value.casefold(), value)
    rows.append(("Unidade", ", ".join(units.values()) or "—"))

    months = sorted({m for f in state.files for m in f.months})
    expected = sorted({m for s in state.slots for m in s.slot.months})
    rows.append(("Período", _period(months, expected)))

    filters: dict[str, str] = {}
    for key in [*spec.pages_expect, *spec.filter_expect, *spec.doctor_pages]:
        for raw in sheets:
            found = raw.page(key) or next((c.value for c in raw.clauses(key) if c.op == "="), None)
            if found:
                filters.setdefault(key, found)
    if isinstance(spec.slots, ValuesSlots):
        values = sorted(
            {v for raw in sheets for c in raw.clauses(spec.slots.filter_key) for v in c.values}
        )
        filters[spec.slots.filter_key] = ", ".join(values)
    rows.append(("Filtros", "; ".join(f"{k}: {v}" for k, v in filters.items()) or "—"))

    names = M.listing((f.original_name for f in state.files), limit=3)
    rows.append(("Ficheiros", f"{len(state.files)} · {names}"))

    total = sum(f.n_rows for f in state.files)
    labels = {s.slot.key: s.slot.label for s in state.slots}
    if len(state.slots) > 1:
        per_slot: dict[str, int] = {}
        for f in state.files:
            for key in f.slot_keys:
                per_slot[labels.get(key, key)] = per_slot.get(labels.get(key, key), 0) + f.n_rows
        detail = " · ".join(f"{k} {number(v)}" for k, v in per_slot.items())
        rows.append(("Linhas", f"{number(total)} ({detail})" if detail else number(total)))
    else:
        rows.append(("Linhas", number(total)))

    sns_cols = spec.header.by_role("sns")
    if sns_cols:
        patients = _distinct_patients(bounds)
        rows.append(("Utentes distintos", number(patients)))
        n_nop = n_none = 0
        for bound in bounds:
            a, b = id_counts(bound)
            n_nop, n_none = n_nop + a, n_none + b
        parts = []
        if n_nop:
            parts.append(f"{number(n_nop)} linha{'s' if n_nop > 1 else ''} (usado NOP)")
        if n_none:
            parts.append(f"{number(n_none)} sem identificação")
        text = "; ".join(parts) or "nenhuma"
        rows.append(("Sem nº SNS", text))

    untitled = sorted({name for b in bounds for _, name in b.untitled_named})
    ignored = sum(c.type == "ignore" for c in spec.header.columns)
    dropped = [c.name for c in spec.header.columns if c.drop]
    col_text = f"{len(spec.header.columns)}"
    if untitled:
        col_text += f" · sem título → {', '.join(untitled)}"
    if ignored:
        col_text += f" · {ignored} ignorada{'s' if ignored > 1 else ''} (Métrica/Mês)"
    if dropped:
        col_text += f" · não guardadas: {', '.join(dropped)}"
    rows.append(("Colunas", col_text))

    footers = sum(f.n_footer for f in state.files)
    if footers:
        rows.append(("Rodapé", f"removido ({footers} linha{'s' if footers > 1 else ''} «Total»)"))

    if isinstance(spec.slots, IcpcSetsSlots):
        target = load_icpc_batches(spec.slots.sets_file).target
        covered = set().union(*(raw.icpc_codes() for raw in sheets)) & target
        rows.append(("Códigos ICPC", f"{len(covered)}/{len(target)}"))
    doctor_cols = spec.header.by_role("doctor", "prescriber")
    if doctor_cols:
        doctors = {
            v
            for b in bounds
            if doctor_cols[0].name in b.data.columns
            for v in b.data[doctor_cols[0].name].drop_nulls().unique().to_list()
            if not is_total(v)
        }
        rows.append(("Médicos", number(len(doctors))))
    return InfoCard(spec.code, spec.title, subtitle, tuple(rows))


def _status_text(state: ReportState) -> str:
    text = STATUS_PT[state.status]
    if state.acknowledged:
        text += " · confirmado («continuar mesmo assim»)"
    n = len(state.issues)
    if n:
        text += f" · {n} problema{'s' if n > 1 else ''}"
    return text


def _distinct_patients(bounds: Sequence[BoundSheet]) -> int:
    """Patients across files: SNS number when valid, otherwise the NOP (TECH_SPECS §5.3)."""
    keys: set[str] = set()
    for bound in bounds:
        spec, data = bound.spec, bound.data
        sns = spec.header.by_role("sns")[0].name
        nop_cols = spec.header.by_role("nop")
        cols = [sns] + ([nop_cols[0].name] if nop_cols and nop_cols[0].name in data.columns else [])
        for row in data.select(cols).iter_rows():
            sns_value = (row[0] or "").strip()
            if sns_value.isdigit() and len(sns_value) == 9:
                keys.add("SNS:" + sns_value)
            elif len(row) > 1 and row[1]:
                keys.add("NOP:" + str(row[1]).strip())
    return len(keys)
