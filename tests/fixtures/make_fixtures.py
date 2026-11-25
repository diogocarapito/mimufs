"""Synthetic MIM@UF-style fixtures. No real patient data, ever (CLAUDE.md rule 2).

Every MIM@UF fixture starts from the **real metadata block and header** of its report, taken
from ``docs/reference/MIMUF_Header_examples.xlsx`` (headers only, anonymised). The year, month,
quarter, unit, doctor and slot values are substituted, and seeded fake rows are appended: SNS
numbers ``9xxxxxxxx`` that belong to no one, names ``Utente 0001``, doctors ``MEDICO
SINTETICO…``. One shared synthetic population feeds every report, so the files join on the
patient key the way a real project does.

Written (``generate``):

* ``valid/<code>/…xls``: one valid file per slot of every MIM@UF report (OOXML saved as ``.xls``,
  like the real exports): 2 + 1 + 1 + 1 + 3 + 3 + 12 + … ≈ 45 files.
* ``variants/``: one ``.xlsx`` copy, one legacy BIFF ``.xls`` (xlwt), one HTML table renamed
  ``.xls`` (V01), the damaged-title header (``1.01.L03.``), and a file with a ``Total`` footer.
* ``sclinico/``: a SClínico-style appointments PDF (layout is a placeholder until Diogo's
  tabula script arrives) and the CSV fallback.
* ``header_examples/``: each sheet of the header workbook as its own file (no data rows).

M1 adds the deliberately broken variants for the V/S checks.

Usage:  uv run python tests/fixtures/make_fixtures.py [OUT_DIR]
Default OUT_DIR: tests/fixtures/generated/ (git-ignored). Tests call :func:`generate` into a
temporary directory instead, so they never depend on a previous manual run.
"""

from __future__ import annotations

import copy
import csv
import datetime as dt
import html
import json
import random
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import openpyxl

from mimufs.core.readers.mimuf_header import (
    FILTER_MARKER,
    PAGES_MARKER,
    TITLE_RE,
    norm,
    parse_filter,
)
from mimufs.core.specs.loader import load_icpc_batches, mimuf_specs, reference_dir
from mimufs.core.specs.models import (
    Column,
    IcpcSetsSlots,
    MimufReportSpec,
    MonthCoverageSlots,
    MonthsSlots,
    ValuesSlots,
    YearSlots,
)
from mimufs.selftest_pdf import make_table_pdf

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADER_EXAMPLES = REPO_ROOT / "docs" / "reference" / "MIMUF_Header_examples.xlsx"
DEFAULT_OUT = Path(__file__).resolve().parent / "generated"

#: Values anonymised in the header workbook, replaced in every fixture.
TEMPLATE_YEAR = "2000"
TEMPLATE_UNIT = "USF Exemplo"
TEMPLATE_DOCTOR = "NOME MEDICO: M 00000"

YEAR = 2024
UNIT = "USF Sintética"
DOCTORS = (
    "MEDICO SINTETICO UM: M 00001",
    "MEDICO SINTETICO DOIS: M 00002",
    "MEDICO SINTETICO TRES: M 00003",
)
PROJECT_DOCTOR = DOCTORS[0]
FREGUESIAS = ("Freguesia Norte", "Freguesia Sul", "Freguesia Centro")
N_PATIENTS = 60
SEED = 20241124

#: Filter values of the ``values`` slots. Only ``651029:Colesterol total, s/l`` and
#: ``Altura(Cm)`` / ``TAd`` are real; the rest are placeholders shaped like them until Diogo
#: sends the exact names (CLAUDE.md "Inputs still needed" #2).
SLOT_VALUES: dict[str, dict[str, str]] = {
    "P07.03.01.L01": {
        "colesterol_total": "651029:Colesterol total, s/l",
        "hdl": "900001:Colesterol HDL, s/l",
        "trigliceridos": "900002:Triglicerídeos, s/l",
        "ldl": "900003:Colesterol LDL, s/l",
        "hba1c": "900004:Hemoglobina A1c, s",
        "creatinina": "900005:Creatinina, s/u",
        "albuminuria": "900006:Albuminúria, u",
    },
    "P10.01.L01": {
        "peso": "Peso(Kg)",
        "altura": "Altura(Cm)",
        "pas": "TAs",
        "pad": "TAd",
        "dm_desde": "DM desde",
    },
}

#: Synthetic result ranges per slot (low, high, decimals): rendered with a decimal comma.
RESULT_RANGES: dict[str, tuple[float, float, int]] = {
    "colesterol_total": (140, 260, 0),
    "hdl": (32, 85, 0),
    "trigliceridos": (60, 320, 0),
    "ldl": (60, 190, 0),
    "hba1c": (5.0, 10.5, 1),
    "creatinina": (0.5, 1.6, 2),
    "albuminuria": (3, 150, 0),
    "peso": (48, 118, 1),
    "altura": (148, 192, 0),
    "pas": (100, 170, 0),
    "pad": (58, 102, 0),
}

#: Common problems, spread over the 3 ICPC code sets.
COMMON_ICPC = (
    "K86", "K87", "T90", "T93", "T82", "P76", "P74", "P17", "R96", "L90", "K77",
    "D84", "F83", "H86", "B80", "A85", "Y85", "X76",
)  # fmt: skip
DIABETES = "T90"
TIPO_RISCO = "Risco de Diabetes Tipo 2"
RISCOS = ("Baixo", "Ligeiramente moderado", "Moderado", "Alto", "Muito alto")

FixtureKind = Literal[
    "valid", "xlsx", "legacy_biff", "not_excel", "damaged_title", "footer",
    "header_example", "sclinico_pdf", "sclinico_csv",
]  # fmt: skip


@dataclass(frozen=True)
class Fixture:
    """One generated file and what the parser must find in it."""

    name: str
    path: Path
    kind: FixtureKind
    code: str | None = None  # report the parser must identify (None: not a MIM@UF export)
    slot: str | None = None  # "2024-01", "2024-T3", "2024", "set2", "altura", "2024-01..12"
    n_rows: int | None = None  # data rows written (footer excluded)
    filter_value: str | None = None  # values slots: the value written in the filter


# ---------------------------------------------------------------------------- population


@dataclass(frozen=True)
class Problem:
    code: str
    since: dt.date


@dataclass(frozen=True)
class Prescription:
    medication: int  # index into the medication list
    day: dt.date
    receitas: int
    embalagens: int


@dataclass(frozen=True)
class Patient:
    n: int
    sns: int
    nop: int
    name: str
    sex: str
    birth: dt.date
    doctor: str
    freguesia: str
    family: int
    in_january: bool  # registered on the January list (P01.01.L01)
    in_december: bool  # still registered in December
    problems: tuple[Problem, ...]
    prescriptions: tuple[Prescription, ...]
    risk: str

    def age(self, on: dt.date) -> int:
        before = (on.month, on.day) < (self.birth.month, self.birth.day)
        return on.year - self.birth.year - before

    @property
    def diabetic(self) -> bool:
        return any(p.code == DIABETES for p in self.problems)


@dataclass(frozen=True)
class Medication:
    name: str
    grupo: str
    dci_code: int

    @property
    def label(self) -> str:
        return f"{self.name.upper()} 10 mg Comp"


@dataclass
class Context:
    year: int
    unit: str
    rng_seed: int
    patients: list[Patient]
    medications: list[Medication]
    icpc_names: dict[str, str]
    indicators: list[tuple[str, str]]
    _cache: dict[str, object] = field(default_factory=dict)

    def rng(self, *key: object) -> random.Random:
        """A deterministic RNG per file (string seeds are stable across runs)."""
        return random.Random(":".join(map(str, (self.rng_seed, *key))))

    @property
    def year_end(self) -> dt.date:
        return dt.date(self.year, 12, 31)

    def icpc_label(self, code: str) -> str:
        return self.icpc_names.get(code, f"PROBLEMA {code}")


def _random_day(rng: random.Random, year: int, months: Sequence[int] = range(1, 13)) -> dt.date:
    return dt.date(year, rng.choice(list(months)), rng.randint(1, 28))


def _load_reference() -> tuple[dict[str, str], list[Medication], list[tuple[str, str]]]:
    dictionaries = reference_dir() / "dictionaries"
    with (dictionaries / "icpc2_pt_v4_4.csv").open(encoding="utf-8") as fh:
        icpc = {row["cod"]: row["nome"].upper() for row in csv.DictReader(fh)}
    with (dictionaries / "medicamentos.csv").open(encoding="utf-8") as fh:
        meds = [
            Medication(row["medicamento"], row["grupo"], 50_000_000 + i)
            for i, row in enumerate(csv.DictReader(fh))
        ]
    with (dictionaries / "indicadores_intervalos.csv").open(encoding="utf-8") as fh:
        indicators = [(row["id_indicador"], row["nome_indicador"]) for row in csv.DictReader(fh)]
    return icpc, meds, indicators


def make_population(
    *, year: int = YEAR, unit: str = UNIT, n_patients: int = N_PATIENTS, seed: int = SEED
) -> Context:
    icpc_names, medications, indicators = _load_reference()
    rng = random.Random(seed)
    patients: list[Patient] = []
    new_problem_month = 0  # round-robin so every month has at least one new problem
    for n in range(1, n_patients + 1):
        birth = dt.date(year - rng.randint(1, 95), rng.randint(1, 12), rng.randint(1, 28))
        problems: list[Problem] = []
        for code in rng.sample(COMMON_ICPC, rng.randint(1, 4)):
            if rng.random() < 0.35:
                new_problem_month = new_problem_month % 12 + 1
                since = dt.date(year, new_problem_month, rng.randint(1, 28))
            else:
                since = dt.date(rng.randint(max(birth.year, year - 20), year - 1), 6, 15)
            problems.append(Problem(code, since))
        prescriptions = tuple(
            Prescription(
                rng.randrange(len(medications)),
                _random_day(rng, year),
                rng.randint(1, 3),
                rng.randint(1, 6),
            )
            for _ in range(rng.randint(0, 5))
        )
        patients.append(
            Patient(
                n=n,
                sns=900_000_000 + n * 7_919,
                nop=4_000_000 + n * 13,
                name=f"Utente {n:04d}",
                sex=rng.choice("FM"),
                birth=birth,
                doctor=DOCTORS[n % len(DOCTORS)],
                freguesia=rng.choice(FREGUESIAS),
                family=(n + 1) // 2,
                in_january=n % 17 != 5,
                in_december=n % 15 != 3,
                problems=tuple(problems),
                prescriptions=prescriptions,
                risk=rng.choice(RISCOS),
            )
        )
    return Context(year, unit, seed, patients, medications, icpc_names, indicators)


# ------------------------------------------------------------------------------ templates


def header_example_rows() -> dict[str, list[list[object]]]:
    """Cell values of every sheet of the real header workbook, keyed by report code."""
    wb = openpyxl.load_workbook(HEADER_EXAMPLES, data_only=True)
    try:
        return {
            ws.title: [list(row) for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets
        }
    finally:
        wb.close()


def _first_text(row: Sequence[object]) -> str:
    return next((str(c) for c in row if c not in (None, "")), "")


def _metadata_layout(rows: Sequence[Sequence[object]]) -> tuple[int, list[int]]:
    """Row index of the filter text and the row indexes of the Páginas lines."""
    texts = [_first_text(r).strip() for r in rows]
    marker = texts.index(FILTER_MARKER)
    filter_idx = next(i for i in range(marker + 1, len(rows)) if texts[i])
    pages: list[int] = []
    if PAGES_MARKER in texts:
        i = texts.index(PAGES_MARKER) + 1
        while i < len(rows) and texts[i]:
            pages.append(i)
            i += 1
    return filter_idx, pages


@dataclass(frozen=True)
class SlotFill:
    """What one fixture file covers: the slot id and the template substitutions."""

    slot: str
    months: tuple[int, ...]  # months of the project year whose data the file holds
    month: int | None = None  # single month (Mês = YYYY-MM)
    quarter: int | None = None  # Trimestre = YYYY-Tn
    month_list: bool = False  # Mês = YYYY-12, …, YYYY-01 (P05.01.L02)
    filter_value: str | None = None  # values slots
    icpc_codes: tuple[str, ...] = ()  # icpc_sets slots


def slot_fills(spec: MimufReportSpec, year: int = YEAR) -> list[SlotFill]:
    """One fill per slot the report needs (TECH_SPECS §6.2)."""
    slots = spec.slots
    if isinstance(slots, MonthsSlots):
        return [SlotFill(f"{year}-{m:02d}", (m,), month=m) for m in slots.months]
    if isinstance(slots, MonthCoverageSlots):
        if slots.display == "quarters":
            return [
                SlotFill(f"{year}-T{q}", tuple(range(3 * q - 2, 3 * q + 1)), quarter=q)
                for q in range(1, 5)
            ]
        months = slots.months
        return [SlotFill(f"{year}-{months[0]:02d}..{months[-1]:02d}", months, month_list=True)]
    if isinstance(slots, YearSlots):
        return [SlotFill(str(year), tuple(range(1, 13)))]
    if isinstance(slots, ValuesSlots):
        values = SLOT_VALUES[spec.code]
        return [
            SlotFill(
                slot_id, (slots.months[0],), month=slots.months[0], filter_value=values[slot_id]
            )
            for slot_id in slots.values
        ]
    if isinstance(slots, IcpcSetsSlots):
        batches = load_icpc_batches(slots.sets_file).batches
        return [
            SlotFill(f"set{b.n}", (slots.months[0],), month=slots.months[0], icpc_codes=b.codes)
            for b in batches
        ]
    raise TypeError(f"unknown slot kind for {spec.code}")


def fill_template(
    template: Sequence[Sequence[object]],
    spec: MimufReportSpec,
    fill: SlotFill,
    ctx: Context,
    *,
    doctor: str = PROJECT_DOCTOR,
    keep_damaged_title: bool = False,
) -> list[list[object]]:
    """The real metadata block + header with this file's year, period, unit and slot."""
    rows = copy.deepcopy([list(r) for r in template])
    filter_idx, page_idxs = _metadata_layout(rows)
    year = str(ctx.year)
    old_slot_value = None
    if fill.filter_value is not None and isinstance(spec.slots, ValuesSlots):
        clauses = parse_filter(norm(str(rows[filter_idx][0])))
        key = spec.slots.filter_key
        old_slot_value = next(c.values[0] for c in clauses if c.key == key)

    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            text = re.sub(rf"\b{TEMPLATE_YEAR}\b", year, cell)
            text = text.replace(TEMPLATE_UNIT, ctx.unit).replace(TEMPLATE_DOCTOR, doctor)
            if fill.month is not None:
                text = re.sub(rf"\b{year}-\d{{2}}\b", f"{year}-{fill.month:02d}", text)
            if fill.month_list:
                listed = ", ".join(f"{year}-{m:02d}" for m in reversed(fill.months))
                text = re.sub(
                    rf"Mês = {year}-\d{{2}}(?:, {year}-\d{{2}})*", f"Mês = {listed}", text
                )
            if fill.quarter is not None:
                quarter = f"{year}-T{fill.quarter}"
                if r in page_idxs and re.match(r"^Mês\s*[:=]", text):
                    text = f"Trimestre: {quarter}"
                else:
                    text = re.sub(rf"Mês = {year}-\d{{2}}", f"Trimestre = {quarter}", text)
            if r == filter_idx and old_slot_value is not None and fill.filter_value is not None:
                text = text.replace(html.escape(old_slot_value, quote=False), fill.filter_value)
            if r == filter_idx and fill.icpc_codes:
                items = ", ".join(f"{code}:{ctx.icpc_label(code)}" for code in fill.icpc_codes)
                text = re.sub(
                    r"\(ICPC = .*\)$", f"(ICPC = {html.escape(items, quote=False)})", text
                )
            row[c] = text

    title = str(rows[0][0])
    if not keep_damaged_title and not TITLE_RE.match(norm(title)):
        rows[0][0] = re.sub(r"^\S+\.\s*", f"{spec.code}. ", title, count=1)
    return rows


# ------------------------------------------------------------------------------- records

Record = dict[str, object]
Rows = list[tuple[Patient | None, Record]]  # (patient or None, report-specific cells)
Producer = Callable[[Context, MimufReportSpec, SlotFill], Rows]


def _decimal_pt(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _registered(ctx: Context, fill: SlotFill) -> list[Patient]:
    """Patients on the list in the file's month (January list ≠ December list)."""
    if fill.months == (1,):
        return [p for p in ctx.patients if p.in_january]
    return [p for p in ctx.patients if p.in_december]


def _p01_l01(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    return [(p, {}) for p in _registered(ctx, fill)]


def _p01_l03(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    rng = ctx.rng(spec.code, fill.slot)
    out: Rows = []
    for p in _registered(ctx, fill):
        out.append(
            (
                p,
                {
                    "Tipo de inscrição atual": "Inscrito",
                    "Motivo Isenção Tx. Moderadora": rng.choice(
                        ("Não isento", "Idade inferior a 18 anos", "Insuficiência económica")
                    ),
                    "Morada": f"Rua Sintética, {p.n}",
                    "Código Postal": "0000-000",
                    "Telefone": "-",
                    "País de Nacionalidade": "Portugal",
                    "Habilitacao Literaria": rng.choice(
                        ("Ensino básico", "Ensino secundário", "Ensino superior")
                    ),
                    "Profissao": f"Profissão {rng.randint(1, 9)}",
                },
            )
        )
    return out


def _p01_l04(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    return [
        (p, {"Local": "Sede", "Data Inscrição": dt.date(max(p.birth.year, ctx.year - 15), 3, 1)})
        for p in _registered(ctx, fill)
    ]


def _p01_l06(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    sizes = Counter(p.family for p in _registered(ctx, fill))
    return [
        (None, {"Local": "Sede", "Família": f"F{family:06d}", "Nº Utentes Familia": size})
        for family, size in sorted(sizes.items())
    ]


def _indicator_rows(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    rng = ctx.rng(spec.code, fill.slot)
    doctors: Sequence[str | None] = DOCTORS if spec.header.by_role("doctor") else (None,)
    out: Rows = []
    for doctor in doctors:
        for ind_id, ind_name in ctx.indicators[:8]:
            rec: Record = {
                "Unidade Funcional / Polo Hospitalar": ctx.unit,
                "Indicador": ind_id,
                "Indicador_2": ind_name,
            }
            if doctor is not None:
                rec["Médico Familia"] = doctor
            den = rng.randint(50, 900)
            num = rng.randint(0, den)
            if "Num." in {c.name for c in spec.header.columns}:
                rec |= {"Num.": float(num), "Den.": float(den), "Valor": round(100 * num / den, 2)}
            else:
                rec |= {
                    "Utentes Cumpridores": num,
                    "Utentes Não Cumpridores": den - num,
                    "Total Utentes": den,
                }
            out.append((None, rec))
    return out


def _icpc_record(ctx: Context, code: str) -> Record:
    return {"ICPC": code, "ICPC_Descricao": ctx.icpc_label(code)}


def _p04_l01(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    wanted = set(fill.icpc_codes)
    return [
        (p, _icpc_record(ctx, prob.code))
        for p in _registered(ctx, fill)
        for prob in p.problems
        if prob.code in wanted
    ]


def _p04_l05(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    (month,) = fill.months
    return [
        (p, {**_icpc_record(ctx, prob.code), "Nº Novos Ut": 1})
        for p in ctx.patients
        for prob in p.problems
        if prob.since.year == ctx.year and prob.since.month == month
    ]


def _problem_counts(ctx: Context) -> list[tuple[str, int]]:
    counts = Counter(prob.code for p in ctx.patients for prob in p.problems)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _p04_r06(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    return [
        (None, {**_icpc_record(ctx, code), "Qtd Problemas": count, "TOP": rank})
        for rank, (code, count) in enumerate(_problem_counts(ctx)[:10], start=1)
    ]


def _p05_r01(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    rng = ctx.rng(spec.code, fill.slot)
    return [
        (None, {**_icpc_record(ctx, code), "Qtd Consultas ICPC": count * rng.randint(1, 4)})
        for code, count in _problem_counts(ctx)
    ]


def _p05_l02(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    out: Rows = []
    for p in ctx.patients:
        if p.diabetic or p.age(ctx.year_end) < 18:
            continue
        month = fill.months[p.n % len(fill.months)]
        out.append(
            (
                p,
                {
                    "Mês": f"{ctx.year}-{month:02d}",
                    "Unidade Funcional / Polo Hospitalar": ctx.unit,
                    "Tipo Risco": TIPO_RISCO,
                    "Risco": p.risk,
                },
            )
        )
    return out


def _p06_l03(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    out: Rows = []
    for p in ctx.patients:
        for rx in p.prescriptions:
            if rx.day.month not in fill.months:
                continue
            med = ctx.medications[rx.medication]
            out.append(
                (
                    p,
                    {
                        "Medicamento/CNPEM": med.label,
                        "Embalagem/CNPEM": "Blister - 30 unidade(s)",
                        "Grupo Farmoterapeutico N3/CNPEM": med.grupo,
                        "Médico": p.doctor,
                        "Médico_2": p.doctor.rsplit(": ", 1)[-1],
                        "Dia Prescrição": rx.day,
                        "Nº Receitas Prescritas": rx.receitas,
                        "Nº Embalagens Prescritas": rx.embalagens,
                    },
                )
            )
    return out


def _p06_r02(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    rng = ctx.rng(spec.code, fill.slot)
    by_med: dict[int, list[tuple[Patient, Prescription]]] = {}
    for p in ctx.patients:
        for rx in p.prescriptions:
            by_med.setdefault(rx.medication, []).append((p, rx))
    out: Rows = []
    for index in sorted(by_med):
        med = ctx.medications[index]
        items = by_med[index]
        embalagens = sum(rx.embalagens for _, rx in items)
        pvp = round(embalagens * rng.uniform(2, 40), 2)
        out.append(
            (
                None,
                {
                    "DCI (CNPEM)": str(med.dci_code),
                    "DCI_Descricao": med.name.capitalize(),
                    "Medicamento": med.label,
                    "Embalagem": "Blister - 30 unidade(s)",
                    "Número Utentes com Prescrição": len({p.n for p, _ in items}),
                    "Nº Receitas Prescritas": sum(rx.receitas for _, rx in items),
                    "Nº Embalagens Prescritas": embalagens,
                    "PVP Medicam Prescritos": pvp,
                    "SNS Medicam Prescritos": round(pvp * 0.6, 2),
                    "Medicam Prescrito / 3º + Barato (Custo - PVP)": round(pvp * 0.1, 2),
                    "Medicam Prescrito / 3º + Barato (Custo - SNS)": round(pvp * 0.06, 2),
                    "Medicam Prescrito / 5º + Barato (Custo - PVP)": round(pvp * 0.05, 2),
                    "Medicam Prescrito / 5º + Barato (Custo - SNS)": round(pvp * 0.03, 2),
                },
            )
        )
    return out


def _p07_01_l01(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    rng = ctx.rng(spec.code, fill.slot)
    exams = list(SLOT_VALUES["P07.03.01.L01"].values())
    out: Rows = []
    for p in ctx.patients:
        for exam in rng.sample(exams, rng.randint(0, 4)):
            rec: Record = {
                "Exame MCDT": exam,
                "Dia Prescrição": _random_day(rng, ctx.year),
                "Nº Exames Prescritos": 1,
            }
            out.append((p, rec))
    return out


def _results(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    """P07.03.01.L01 / P10.01.L01: the last result of the period, one row per patient."""
    rng = ctx.rng(spec.code, fill.slot)
    date_col, value_col = (
        ("Data Último MCDT", "Resultado Último MCDT")
        if spec.code == "P07.03.01.L01"
        else ("Data Último Registo", "Resultado Último Registo")
    )
    out: Rows = []
    for p in _registered(ctx, fill):
        if fill.slot in {"hba1c", "dm_desde"} and not p.diabetic:
            continue
        if fill.slot not in {"hba1c", "dm_desde"} and rng.random() < 0.2:
            continue  # no record in the period
        if fill.slot == "dm_desde":
            since = next(prob.since for prob in p.problems if prob.code == DIABETES)
            value = str(since.year)
        else:
            low, high, decimals = RESULT_RANGES[fill.slot]
            value = _decimal_pt(rng.uniform(low, high), decimals)
        out.append((p, {date_col: _random_day(rng, ctx.year), value_col: value}))
    return out


PRODUCERS: dict[str, Producer] = {
    "P01.01.L01": _p01_l01,
    "P01.01.L03": _p01_l03,
    "P01.01.L04": _p01_l04,
    "P01.01.L06": _p01_l06,
    "P02.01.R01": _indicator_rows,
    "P02.01.R03": _indicator_rows,
    "P02.01.R04": _indicator_rows,
    "P04.01.L01": _p04_l01,
    "P04.01.L05": _p04_l05,
    "P04.R06": _p04_r06,
    "P05.01.L02": _p05_l02,
    "P05.R01": _p05_r01,
    "P06.01.01.L03": _p06_l03,
    "P06.01.R02": _p06_r02,
    "P07.01.01.L01": _p07_01_l01,
    "P07.03.01.L01": _results,
    "P10.01.L01": _results,
}


def _default_producer(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> Rows:
    """A report added later without a dedicated producer: one row per registered patient."""
    if spec.id_columns:
        return [(p, {}) for p in _registered(ctx, fill)]
    return [(None, {}) for _ in range(5)]


def _patient_value(col: Column, p: Patient, on: dt.date) -> object:
    match col.role:
        case "sns":
            return p.sns
        case "nop":
            return p.nop
        case "doctor":
            return p.doctor
    return {
        "Nome": p.name,
        "Sexo": p.sex,
        "Idade": p.age(on),
        "Data Nascimento": p.birth,
        "Freguesia Habitação": p.freguesia,
    }.get(col.name)


def _fallback(col: Column, rng: random.Random, year: int) -> object:
    """Any column no producer filled (keeps new specs working without new Python)."""
    match col.type:
        case "int":
            return rng.randint(1, 20)
        case "float":
            return round(rng.uniform(1, 100), 2)
        case "date":
            return _random_day(rng, year)
        case "cat":
            return f"Categoria {rng.randint(1, 3)}"
    return f"{col.name} {rng.randint(1, 9)}"


def data_rows(ctx: Context, spec: MimufReportSpec, fill: SlotFill) -> list[list[object]]:
    producer = PRODUCERS.get(spec.code, _default_producer)
    rng = ctx.rng(spec.code, fill.slot, "fallback")
    on = dt.date(ctx.year, max(fill.months), 28)
    width = spec.header.width
    rows: list[list[object]] = []
    for patient, record in producer(ctx, spec, fill):
        row: list[object] = [None] * width
        for col in spec.header.columns:
            if col.type == "ignore":
                continue
            if col.name in record:
                value = record[col.name]
            elif patient is not None and (v := _patient_value(col, patient, on)) is not None:
                value = v
            elif col.role == "unit":
                value = ctx.unit
            else:
                value = _fallback(col, rng, ctx.year)
            row[col.at] = value
        rows.append(row)
    return rows


# --------------------------------------------------------------------------------- writers


def _save(wb: openpyxl.Workbook, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:  # a handle: openpyxl refuses to save to a ".xls" path
        wb.save(fh)
    return path


def write_rows(
    path: Path, rows: Iterable[Sequence[object]], sheet_title: str = "Relatório"
) -> Path:
    """Write rows to an OOXML workbook (any extension; MIM@UF uses ``.xls``)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet_title
    for row in rows:
        ws.append(list(row))
    return _save(wb, path)


def write_biff(
    path: Path, rows: Iterable[Sequence[object]], sheet_title: str = "Relatório"
) -> Path:
    """Write rows to a legacy BIFF8 ``.xls`` (xlwt; only for the legacy-format fixture)."""
    import xlwt  # dev-only dependency

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet(sheet_title)
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if value is None:
                continue
            if isinstance(value, dt.date):
                ws.write(r, c, value, date_style)
            else:
                ws.write(r, c, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def write_html_table(path: Path, rows: Iterable[Sequence[object]]) -> Path:
    """An HTML table saved with an ``.xls`` name: not an Excel file (check V01)."""
    body = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c or ''))}</td>" for c in row) + "</tr>"
        for row in rows
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<html><body><table>\n{body}\n</table></body></html>\n", encoding="utf-8")
    return path


def split_header_examples(out_dir: Path) -> dict[str, Path]:
    """Save each sheet of the header workbook as its own ``<code>.xls`` (OOXML) file."""
    return {
        code: write_rows(out_dir / "header_examples" / f"{code}.xls", rows)
        for code, rows in header_example_rows().items()
    }


def _file_stem(spec: MimufReportSpec, fill: SlotFill) -> str:
    return f"{spec.code}_{fill.slot}".replace("..", "-")


# ---------------------------------------------------------------------------------- SClínico

SCLINICO_PDF_HEADER = ("Data", "N.º Utente", "NOP", "Profissional", "Tipo de Consulta", "Local")
TIPOS_CONSULTA = (
    "Consulta de Saúde de Adultos",
    "Consulta de Diabetes",
    "Consulta de Hipertensão",
    "Consulta Aberta",
    "Consulta Não Presencial",
)


def sclinico_rows(ctx: Context) -> list[tuple[dt.date, Patient, str, str]]:
    rng = ctx.rng("sclinico")
    rows = [
        (_random_day(rng, ctx.year), p, rng.choice(TIPOS_CONSULTA), rng.choice(("Sede", "Polo")))
        for p in ctx.patients
        for _ in range(rng.randint(0, 4))
    ]
    return sorted(rows, key=lambda r: (r[0], r[1].n))


def write_sclinico(ctx: Context, out_dir: Path) -> list[Fixture]:
    rows = sclinico_rows(ctx)
    folder = out_dir / "sclinico"
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / f"consultas_{ctx.year}.pdf"
    pdf.write_bytes(
        make_table_pdf(
            SCLINICO_PDF_HEADER,
            [
                (d.strftime("%d-%m-%Y"), str(p.sns), str(p.nop), p.doctor, tipo, local)
                for d, p, tipo, local in rows
            ],
            widths=(1, 1, 1, 2.2, 2.2, 0.8),
        )
    )
    csv_path = folder / f"consultas_{ctx.year}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(
            ["data_consulta", "utente", "nop", "profissional", "tipo_consulta", "local"]
        )
        writer.writerows(
            (d.isoformat(), p.sns, p.nop, p.doctor, tipo, local) for d, p, tipo, local in rows
        )
    return [
        Fixture(
            "sclinico/pdf", pdf, "sclinico_pdf", "SCLINICO.consultas", str(ctx.year), len(rows)
        ),
        Fixture(
            "sclinico/csv", csv_path, "sclinico_csv", "SCLINICO.consultas", str(ctx.year), len(rows)
        ),
    ]


# ---------------------------------------------------------------------------------- generate


def generate(
    out_dir: Path,
    *,
    year: int = YEAR,
    unit: str = UNIT,
    n_patients: int = N_PATIENTS,
    seed: int = SEED,
) -> dict[str, Fixture]:
    """Write every fixture into ``out_dir``; returns name -> :class:`Fixture`."""
    ctx = make_population(year=year, unit=unit, n_patients=n_patients, seed=seed)
    templates = header_example_rows()
    specs = mimuf_specs()
    fixtures: list[Fixture] = []

    for code, path in split_header_examples(out_dir).items():
        fixtures.append(Fixture(f"header/{code}", path, "header_example", code, None, 0))

    rows_by_name: dict[str, list[list[object]]] = {}
    for code, spec in sorted(specs.items()):
        for fill in slot_fills(spec, year):
            meta = fill_template(templates[code], spec, fill, ctx)
            data = data_rows(ctx, spec, fill)
            name = f"valid/{code}/{fill.slot}"
            rows_by_name[name] = meta + data
            path = write_rows(
                out_dir / "valid" / code / f"{_file_stem(spec, fill)}.xls", meta + data
            )
            fixtures.append(
                Fixture(name, path, "valid", code, fill.slot, len(data), fill.filter_value)
            )

    variants = out_dir / "variants"
    dec = f"valid/P01.01.L01/{year}-12"
    base = rows_by_name[dec]
    n_dec = next(f.n_rows for f in fixtures if f.name == dec)
    fixtures += [
        Fixture(
            "variants/xlsx",
            write_rows(
                variants / "P10.01.L01_altura.xlsx", rows_by_name["valid/P10.01.L01/altura"]
            ),
            "xlsx",
            "P10.01.L01",
            "altura",
            next(f.n_rows for f in fixtures if f.name == "valid/P10.01.L01/altura"),
            SLOT_VALUES["P10.01.L01"]["altura"],
        ),
        Fixture(
            "variants/legacy_biff",
            write_biff(variants / f"P01.01.L01_{year}-12_biff.xls", base),
            "legacy_biff",
            "P01.01.L01",
            f"{year}-12",
            n_dec,
        ),
        Fixture(
            "variants/footer",
            write_rows(
                variants / f"P01.01.L01_{year}-12_footer.xls",
                [*base, ["Total", None, None, None, None, None, None, n_dec]],
            ),
            "footer",
            "P01.01.L01",
            f"{year}-12",
            n_dec,
        ),
        Fixture(
            "variants/not_excel",
            write_html_table(variants / "relatorio_html.xls", base),
            "not_excel",
        ),
    ]
    l03 = specs["P01.01.L03"]
    (l03_fill,) = slot_fills(l03, year)
    damaged = fill_template(templates["P01.01.L03"], l03, l03_fill, ctx, keep_damaged_title=True)
    l03_data = data_rows(ctx, l03, l03_fill)
    fixtures.append(
        Fixture(
            "variants/damaged_title",
            write_rows(variants / f"P01.01.L03_{year}-12_damaged_title.xls", damaged + l03_data),
            "damaged_title",
            "P01.01.L03",
            l03_fill.slot,
            len(l03_data),
        )
    )
    fixtures += write_sclinico(ctx, out_dir)

    manifest = {
        f.name: {
            "path": f.path.relative_to(out_dir).as_posix(),
            "kind": f.kind,
            "code": f.code,
            "slot": f.slot,
            "n_rows": f.n_rows,
        }
        for f in fixtures
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return {f.name: f for f in fixtures}


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    fixtures = generate(out)
    if str(REPO_ROOT) not in sys.path:  # run as a script: make `tests` importable
        sys.path.insert(0, str(REPO_ROOT))
    from tests.fixtures import broken

    scenarios = broken.generate_scenarios(out)
    print(f"{len(fixtures)} fixtures and {len(scenarios)} broken scenarios written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
