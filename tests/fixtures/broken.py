"""Deliberately broken MIM@UF fixtures for checks V01–V12 and S01–S04 (M1 "Done when").

Each :class:`Scenario` is the complete, valid set of files of one report with **one** targeted
mutation (a wrong unit, a month outside the year, another doctor's page, a missing column…),
plus the exact set of ``(check_id, severity)`` it must produce and PT-PT text the messages must
contain. Import-level scenarios (V01, V02) have ``code=None``: their file is never stored.

Synthetic data only (CLAUDE.md rule 2): the files are built from the same population and real
header templates as the valid fixtures.
"""

from __future__ import annotations

import copy
import dataclasses
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from mimufs.core.specs.loader import mimuf_specs
from mimufs.core.specs.models import MimufReportSpec
from mimufs.core.validation.result import Status
from tests.fixtures import make_fixtures as mf

E, W = Status.ERROR, Status.WARNING
RowsT = list[list[object]]


@dataclass(frozen=True)
class Scenario:
    name: str
    code: str | None  # report the files belong to; None = rejected at import (V01/V02)
    files: tuple[Path, ...]
    expect: frozenset[tuple[str, Status]]  # exactly these (check_id, severity) pairs
    contains: tuple[str, ...] = ()  # PT-PT snippets that must appear in the messages
    mutated: str | None = None  # file name of the mutated file


# ------------------------------------------------------------------------------ row edits


def _layout(rows: RowsT) -> tuple[int, list[int], int]:
    """(filter row, Páginas rows, first header row) of a sheet built from a template."""
    filter_idx, pages = mf._metadata_layout(rows)
    start = max([filter_idx, *pages]) + 1
    header = next(
        i for i in range(start, len(rows)) if sum(c not in (None, "") for c in rows[i]) >= 2
    )
    return filter_idx, pages, header


def set_filter(rows: RowsT, old: str, new: str) -> RowsT:
    f, _, _ = _layout(rows)
    text = str(rows[f][0])
    assert old in text, (old, text)
    rows[f][0] = text.replace(old, new)
    return rows


def set_page(rows: RowsT, key: str, value: str) -> RowsT:
    _, pages, _ = _layout(rows)
    for i in pages:
        cell = str(rows[i][0])
        if cell.startswith((f"{key}:", f"{key} =")):
            rows[i][0] = f"{key}: {value}"
            return rows
    rows.insert(pages[-1] + 1, [f"{key}: {value}"])
    return rows


def drop_page(rows: RowsT, key: str) -> RowsT:
    _, pages, _ = _layout(rows)
    for i in pages:
        cell = str(rows[i][0])
        if cell.startswith((f"{key}:", f"{key} =")):
            del rows[i]
            return rows
    raise AssertionError(f"no page line {key!r}")


def delete_column(rows: RowsT, at: int) -> RowsT:
    _, _, header = _layout(rows)
    for row in rows[header:]:
        if len(row) > at:
            del row[at]
    return rows


def add_column(rows: RowsT, title: str, value: object) -> RowsT:
    _, _, header = _layout(rows)
    width = max(len(r) for r in rows[header:])
    for i, row in enumerate(rows[header:]):
        row.extend([None] * (width - len(row)))
        row.append(title if i == 0 else value)
    return rows


def set_header(rows: RowsT, at: int, title: str) -> RowsT:
    _, _, header = _layout(rows)
    rows[header][at] = title
    return rows


def drop_data(rows: RowsT, header_rows: int = 1) -> RowsT:
    _, _, header = _layout(rows)
    del rows[header + header_rows :]
    return rows


# ---------------------------------------------------------------------------- the builder


class Builder:
    def __init__(self, out_dir: Path) -> None:
        self.out = out_dir / "broken"
        self.ctx = mf.make_population()
        self.templates = mf.header_example_rows()
        self.specs = mimuf_specs()
        self.scenarios: dict[str, Scenario] = {}

    def rows(
        self,
        code: str,
        slot: str,
        *,
        unit: str | None = None,
        doctor: str = mf.PROJECT_DOCTOR,
        fill: mf.SlotFill | None = None,
    ) -> RowsT:
        spec = self.specs[code]
        fill = fill or next(f for f in mf.slot_fills(spec) if f.slot == slot)
        ctx = dataclasses.replace(self.ctx, unit=unit) if unit else self.ctx
        meta = mf.fill_template(self.templates[code], spec, fill, ctx, doctor=doctor)
        return meta + mf.data_rows(ctx, spec, fill)

    def valid_set(self, code: str) -> dict[str, RowsT]:
        return {f.slot: self.rows(code, f.slot) for f in mf.slot_fills(self.specs[code])}

    def add(
        self,
        name: str,
        code: str,
        expect: Sequence[tuple[str, Status]],
        *,
        mutate: tuple[str, Callable[[RowsT], RowsT]] | None = None,
        drop: Sequence[str] = (),
        extra: Sequence[tuple[str, RowsT]] = (),
        contains: Sequence[str] = (),
    ) -> None:
        """The report's valid set, minus ``drop`` slots, with one slot mutated, plus extras."""
        spec: MimufReportSpec = self.specs[code]
        folder = self.out / name
        if folder.exists():
            shutil.rmtree(folder)
        files: list[Path] = []
        mutated = None
        for slot, rows in self.valid_set(code).items():
            if slot in drop:
                continue
            stem = f"{code}_{slot}".replace("..", "-").replace("/", "_")
            if mutate and mutate[0] == slot:
                rows = mutate[1](copy.deepcopy(rows))
                stem += "_mutado"
                mutated = f"{stem}.xls"
            files.append(mf.write_rows(folder / f"{stem}.xls", rows))
        for stem, rows in extra:
            files.append(mf.write_rows(folder / f"{stem}.xls", rows))
        assert spec.code == code
        self.scenarios[name] = Scenario(
            name, code, tuple(files), frozenset(expect), tuple(contains), mutated
        )

    def add_single(
        self,
        name: str,
        path: Path,
        expect: Sequence[tuple[str, Status]],
        contains: Sequence[str] = (),
    ) -> None:
        self.scenarios[name] = Scenario(
            name, None, (path,), frozenset(expect), tuple(contains), path.name
        )


def generate_scenarios(out_dir: Path) -> dict[str, Scenario]:
    b = Builder(out_dir)
    y = mf.YEAR
    other_doctor = "OUTRO MEDICO: M 99999"

    # V01 / V02 — rejected at import
    folder = b.out / "import"
    folder.mkdir(parents=True, exist_ok=True)
    html = mf.write_html_table(folder / "pagina_web.xls", b.rows("P01.01.L01", f"{y}-12"))
    b.add_single("V01_html", html, [("V01", E)], ["não é um Excel verdadeiro"])
    corrupt = folder / "danificado.xls"
    corrupt.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
    b.add_single("V01_corrupt", corrupt, [("V01", E)], ["danificado"])
    plain = mf.write_rows(folder / "tabela_simples.xlsx", [["Utente", "Nome"], ["900000001", "X"]])
    b.add_single("V01_no_header", plain, [("V01", E)], ["cabeçalho de um relatório do MIM@UF"])
    unknown_rows = [
        ["P99.99.L99. Relatório inventado"],
        [],
        ["Filtro do relatório:"],
        ["Mês = 2024-12"],
        [],
        ["Coluna A", "Coluna B"],
        ["1", "2"],
    ]
    unknown = mf.write_rows(folder / "desconhecido.xls", unknown_rows)
    b.add_single("V02_unknown", unknown, [("V02", E)], ["Relatório não reconhecido"])

    # V03 — unit (the other files keep the project unit: S03 sees two units)
    b.add(
        "V03_wrong_unit",
        "P10.01.L01",
        [("V03", E), ("S03", E)],
        mutate=("altura", lambda r: b.rows("P10.01.L01", "altura", unit="USF Vizinha")),
        contains=["«USF Vizinha» é diferente da do projeto"],
    )

    # V04 — period and slot
    b.add(
        "V04_outside_year",
        "P04.01.L05",
        [("V04", E), ("S01", W)],
        mutate=(
            f"{y}-07",
            lambda r: set_page(set_filter(r, f"{y}-07", f"{y - 1}-07"), "Mês", f"{y - 1}-07"),
        ),
        contains=[f"{y - 1}-07 está fora do ano do projeto", "Jul"],
    )
    b.add(
        "V04_unexpected_month",
        "P01.01.L01",
        [("V04", W), ("S01", W)],
        mutate=(
            f"{y}-12",
            lambda r: set_page(set_filter(r, f"{y}-12", f"{y}-06"), "Mês", f"{y}-06"),
        ),
        contains=["não é um dos meses pedidos", "Dez"],
    )
    b.add(
        "V04_unknown_value",
        "P10.01.L01",
        [("V04", W), ("S01", W)],
        mutate=("pas", lambda r: set_filter(r, "TAs", "Perímetro abdominal")),
        contains=["«Perímetro abdominal» não corresponde", "PAs"],
    )
    b.add(
        "V04_no_period",
        "P04.R06",
        [("V04", E), ("S01", W)],
        mutate=(
            f"{y}-12",
            lambda r: drop_page(set_filter(r, f"Mês = {y}-12", f"Ano Civil = {y}"), "Mês"),
        ),
        contains=["Não foi possível ler o período"],
    )
    b.add(
        "V04_unknown_icpc_set",
        "P04.01.L01",
        [("V04", W), ("S02", W)],
        mutate=("set3", lambda r: _icpc_filter(r, "-30:EXAME MÉDICO COMPLETO, -31:EXAME PARCIAL")),
        contains=["não correspondem a nenhum dos lotes", "Falta o lote 3"],
    )

    # V05 — filter vs pages
    b.add(
        "V05_filter_vs_pages",
        "P01.01.L01",
        [("V05", W)],
        mutate=(f"{y}-01", lambda r: set_page(r, "Mês", f"{y}-12")),
        contains=[f"O filtro indica Mês = {y}-01, mas as páginas indicam {y}-12"],
    )

    # V06 — required values and doctor pages
    b.add(
        "V06_flag_value",
        "P01.01.L01",
        [("V06", W), ("S03", E)],
        mutate=(f"{y}-12", lambda r: set_page(r, "Flag Médico Família", "Total")),
        contains=["Flag Médico Família devia ser «C/ Med Fam»"],
    )
    b.add(
        "V06_missing_value",
        "P01.01.L01",
        [("V06", W)],
        mutate=(f"{y}-12", lambda r: drop_page(r, "Frequentador")),
        contains=["Não foi possível confirmar Frequentador = Total"],
    )
    b.add(
        "V06_other_doctor",
        "P04.01.L05",
        [("V06", E)],
        mutate=(f"{y}-03", lambda r: b.rows("P04.01.L05", f"{y}-03", doctor=other_doctor)),
        contains=["página de outro médico", other_doctor],
    )
    b.add(
        "V06_no_slot_filter",
        "P10.01.L01",
        [("V06", E), ("S01", W)],
        mutate=("peso", lambda r: set_filter(r, "({Tipo Dado} = Peso(Kg)) E ", "")),
        contains=["Falta o filtro Tipo Dado", "Peso"],
    )

    # V07 — columns
    b.add(
        "V07_missing_column",
        "P10.01.L01",
        [("V07", E), ("S04", E)],
        mutate=("pad", lambda r: delete_column(r, 3)),
        contains=["devia ser «Sexo», mas é «Idade»"],
    )
    b.add(
        "V07_blank_header",
        "P01.01.L03",
        [("V07", E)],
        mutate=(f"{y}-12", lambda r: set_header(r, 5, "")),
        contains=["devia ser «Idade», mas está sem título"],
    )
    b.add(
        "V07_extra_column",
        "P01.01.L04",
        [("V07", W)],
        mutate=(f"{y}-12", lambda r: add_column(r, "Observações", "—")),
        contains=["Coluna inesperada «Observações»"],
    )

    # V08 — empty
    b.add(
        "V08_empty",
        "P04.R06",
        [("V08", W)],
        mutate=(f"{y}-12", drop_data),
        contains=["Relatório vazio"],
    )

    # V10 — patient IDs: 2 rows fall back to the NOP, 1 row has no ID at all
    b.add(
        "V10_ids",
        "P10.01.L01",
        [("V10", W)],
        mutate=("dm_desde", _blank_ids),
        contains=["2 linhas", "usam o NOP", "1 linha não tem"],
    )

    # V11 — duplicates
    l03 = b.rows("P01.01.L03", f"{y}-12")
    b.add(
        "V11_same_file",
        "P01.01.L03",
        [("V11", W)],
        extra=[("P01.01.L03_copia", copy.deepcopy(l03))],
        contains=["Ficheiro idêntico"],
    )
    shorter = b.rows("P10.01.L01", "altura")[:-5]
    b.add(
        "V11_same_slot",
        "P10.01.L01",
        [("V11", W)],
        extra=[("P10.01.L01_altura_outra", shorter)],
        contains=["A extração Altura já tem"],
    )

    # V12 — footer: removed, not an issue
    def footer(r: RowsT) -> RowsT:
        return [*r, ["Total", *([None] * 14), 56]]

    b.add("V12_footer", "P01.01.L03", [], mutate=(f"{y}-12", footer))

    # S01 — completeness and coverage
    b.add(
        "S01_missing_month",
        "P04.01.L05",
        [("S01", W)],
        drop=[f"{y}-07"],
        contains=["Falta 1 extração: Jul"],
    )
    b.add(
        "S01_coverage_gap",
        "P06.01.01.L03",
        [("S01", W)],
        drop=[f"{y}-T3"],
        contains=[f"Meses sem dados: Jul {y}, Ago {y}, Set {y}"],
    )
    feb = b.rows("P06.01.01.L03", "", fill=mf.SlotFill(f"{y}-02", (2,), month=2))
    b.add(
        "S01_coverage_overlap",
        "P06.01.01.L03",
        [("S01", W)],
        extra=[("P06.01.01.L03_fevereiro", feb)],
        contains=[f"Meses em mais de um ficheiro: Fev {y}"],
    )

    # S02 — ICPC coverage
    b.add(
        "S02_missing_set",
        "P04.01.L01",
        [("S02", W)],
        drop=["set3"],
        contains=["Falta o lote 3 (S74 → Z29, 232 códigos)"],
    )

    # S04 — structure (one month exported with an extra column)
    b.add(
        "S04_structure",
        "P04.01.L05",
        [("V07", W), ("S04", E)],
        mutate=(f"{y}-05", lambda r: add_column(r, "Observações", "—")),
        contains=["não têm as mesmas colunas"],
    )
    return b.scenarios


def _icpc_filter(rows: RowsT, items: str) -> RowsT:
    f, _, _ = _layout(rows)
    text = str(rows[f][0])
    start = text.index("(ICPC = ")
    rows[f][0] = text[:start] + f"(ICPC = {items})"
    return rows


def _blank_ids(rows: RowsT) -> RowsT:
    _, _, header = _layout(rows)
    data = rows[header + 1 :]
    for row in data[:2]:
        row[1] = None  # Utente blank, NOP kept
    data[2][0] = None  # neither NOP…
    data[2][1] = None  # …nor Utente
    return rows
