"""MIM@UF header/filter parser (TECH_SPECS §5.1-5.2), on the real headers and edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from mimufs.core.readers.excel import FileFormat, SheetRows
from mimufs.core.readers.mimuf_header import (
    HeaderParseError,
    bind_columns,
    parse_filter,
    parse_page_line,
    parse_sheet,
    read_mimuf_file,
)
from mimufs.core.specs import mimuf_specs
from tests.fixtures.make_fixtures import write_rows

# ------------------------------------------------------------------- every real header


def test_header_workbook_has_every_mimuf_report(header_example_files: dict[str, Path]) -> None:
    assert set(header_example_files) == set(mimuf_specs())


@pytest.mark.parametrize("code", sorted(mimuf_specs()))
def test_real_header_parses_and_binds(code: str, header_example_files: dict[str, Path]) -> None:
    raw = read_mimuf_file(header_example_files[code])
    assert raw.code == code
    assert raw.format is FileFormat.OOXML
    assert raw.spec is not None
    assert raw.n_rows == 0  # the workbook holds headers only, never patient rows
    bound = bind_columns(raw, raw.spec)
    assert bound.mismatches == ()
    assert bound.extra_columns == ()
    expected = [c.name for c in raw.spec.header.columns if c.type != "ignore" and not c.drop] + [
        "_row"
    ]
    assert bound.data.columns == expected
    assert raw.filter, "every export has a filter"
    assert raw.has_pages is (not raw.spec.no_pages)


def test_damaged_title_found_by_title_text_and_signature(
    header_example_files: dict[str, Path],
) -> None:
    raw = read_mimuf_file(header_example_files["P01.01.L03"])
    assert raw.title_raw.startswith("1.01.L03.")  # the real example is damaged
    assert raw.code == "P01.01.L03"
    assert raw.code_source == "title_text"
    assert raw.title == "Inscritos > Dados dos Utentes"


def test_unknown_title_found_by_header_signature(
    tmp_path: Path, header_example_rows: dict[str, list[list[object]]]
) -> None:
    rows = [list(r) for r in header_example_rows["P10.01.L01"]]
    rows[0] = ["Relatório sem título reconhecível"]
    raw = read_mimuf_file(write_rows(tmp_path / "x.xls", rows))
    assert raw.code == "P10.01.L01"
    assert raw.code_source == "header_signature"


def test_contact_columns_dropped_before_storage(header_example_files: dict[str, Path]) -> None:
    raw = read_mimuf_file(header_example_files["P01.01.L03"])
    assert {"c9", "c10", "c11"}.isdisjoint(raw.rows.columns)
    bound = bind_columns(raw, raw.spec)  # type: ignore[arg-type]
    assert {"Morada", "Código Postal", "Telefone"}.isdisjoint(bound.data.columns)


def test_untitled_columns_named_by_position(header_example_files: dict[str, Path]) -> None:
    raw = read_mimuf_file(header_example_files["P04.01.L01"])
    bound = bind_columns(raw, raw.spec)  # type: ignore[arg-type]
    assert dict(bound.untitled_named) == {2: "Nome", 6: "ICPC_Descricao"}


def test_two_header_rows(header_example_files: dict[str, Path]) -> None:
    raw = read_mimuf_file(header_example_files["P02.01.R04"])
    assert raw.header2 is not None
    assert raw.header2[7:10] == ("Utentes Cumpridores", "Utentes Não Cumpridores", "Total Utentes")


# ------------------------------------------------------------------------------- filters


def test_basic_filter_and_aliases() -> None:
    clauses = parse_filter(
        "(Mês = 2000-01) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo)"
    )
    assert [(c.key, c.op, c.values) for c in clauses] == [
        ("Mês", "=", ("2000-01",)),
        ("Unidade Funcional / Polo Hospitalar", "=", ("USF Exemplo",)),
    ]
    assert [c.alias for c in clauses] == ["mes", "unidade"]


@pytest.mark.parametrize("text", ["Mês = 2000-12", "Ano = 2000"])
def test_clause_without_parentheses(text: str) -> None:
    (clause,) = parse_filter(text)
    assert clause.op == "="
    assert clause.alias in ("mes", "ano")


def test_escaped_operators_and_braced_keys() -> None:
    clauses = parse_filter(
        "({Alvo Indicador} = Utente) E ({Tipo Indicador} &lt;&gt; ACES, Indicadores das "
        "Unidades de Cuidados na Comunidade) E (Mês = 2000-02) E ({Nº Novos Utentes} &gt; 0)"
    )
    assert [(c.key, c.op) for c in clauses] == [
        ("Alvo Indicador", "="),
        ("Tipo Indicador", "<>"),
        ("Mês", "="),
        ("Nº Novos Utentes", ">"),
    ]
    # Not a recognised list: the value is kept whole.
    assert clauses[1].values == ("ACES, Indicadores das Unidades de Cuidados na Comunidade",)


def test_month_list_and_key_suffix() -> None:
    clauses = parse_filter(
        "(Mês = 2000-11, 2000-10, 2000-09, 2000-08, 2000-07, 2000-06, 2000-05, 2000-04, "
        "2000-03, 2000-02, 2000-01) E ({Unidade Funcional / Polo Hospitalar} = USF Exemplo) "
        "E ({Tipo Risco} (ID) = -24)"
    )
    assert len(clauses[0].values) == 11
    assert clauses[0].values[0] == "2000-11"
    assert (clauses[2].key, clauses[2].values) == ("Tipo Risco (ID)", ("-24",))


def test_exam_value_with_comma_kept_whole() -> None:
    clauses = parse_filter(
        "({Exame MCDT} = 651029:Colesterol total, s/l) E (Mês = 2000-12) E "
        "({Unidade Funcional / Polo Hospitalar} = USF Exemplo)"
    )
    assert clauses[0].values == ("651029:Colesterol total, s/l",)


def test_quarter_filter() -> None:
    clauses = parse_filter("(Trimestre = 2024-T3) E ({Unidade Funcional} = USF Exemplo)")
    assert (clauses[0].alias, clauses[0].values) == ("trimestre", ("2024-T3",))


def test_icpc_list_with_commas_and_parentheses(header_example_files: dict[str, Path]) -> None:
    raw = read_mimuf_file(header_example_files["P04.01.L01"])
    (icpc,) = raw.clauses("ICPC")
    assert len(icpc.values) == 30
    assert "A79:CARCINOMATOSE (LOCALIZAÇÃO PRIMÁRIA DESCONHECIDA), NE" in icpc.values
    assert "A77:OUTRA DOENÇA VIRAL, NE" in icpc.values
    assert {"A96", "B26", "B72"} <= raw.icpc_codes()
    assert len(raw.icpc_codes()) == 30


def test_icpc_codes_only_list() -> None:
    (clause,) = parse_filter("ICPC = A01, A02, A03")
    assert clause.values == ("A01", "A02", "A03")


def test_unbalanced_parentheses_fall_back_to_clause_boundaries() -> None:
    clauses = parse_filter(
        "(Mês = 2000-12) E (ICPC = A01:DOR (GENERALIZADA, A02:ARREPIOS) E "
        "({Unidade Funcional} = USF Exemplo)"
    )
    assert [c.key for c in clauses] == ["Mês", "ICPC", "Unidade Funcional"]
    assert clauses[1].values[0] == "A01:DOR (GENERALIZADA"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Mês: 2000-01", ("Mês", "2000-01")),
        ("Mês = 2000-12", ("Mês", "2000-12")),
        ("Médico de Registo: NOME MEDICO: M 00000", ("Médico de Registo", "NOME MEDICO: M 00000")),
        ("Unidade Funcional: Total", ("Unidade Funcional", "Total")),
    ],
)
def test_page_lines(line: str, expected: tuple[str, str]) -> None:
    assert parse_page_line(line) == expected


# ----------------------------------------------------------------------- effective values


def test_page_total_never_conflicts_with_filter(header_example_files: dict[str, Path]) -> None:
    raw = read_mimuf_file(header_example_files["P06.01.01.L03"])
    assert raw.page("unidade") == "Total"
    assert raw.effective("unidade") == ("USF Exemplo",)
    assert raw.effective("mes") == ("2000-12",)


def test_unit_from_column_when_absent_from_metadata(
    header_example_files: dict[str, Path],
) -> None:
    raw = read_mimuf_file(header_example_files["P02.01.R01"])
    assert raw.effective("unidade") == ()
    assert raw.effective("unidade", ["USF Exemplo", "USF Exemplo"]) == ("USF Exemplo",)


def test_doctor_page_value_with_colon(header_example_files: dict[str, Path]) -> None:
    raw = read_mimuf_file(header_example_files["P04.01.L05"])
    assert raw.page("Médico de Registo") == "NOME MEDICO: M 00000"
    assert raw.page("Médico Familia") == "Total"


def test_no_pages_section(header_example_files: dict[str, Path]) -> None:
    raw = read_mimuf_file(header_example_files["P05.01.L02"])
    assert not raw.has_pages
    assert raw.pages == {}
    assert raw.header[:2] == ("Mês", "Unidade Funcional / Polo Hospitalar")


# ------------------------------------------------------------------------ data and footer


def _with_data(rows: list[list[object]], data: list[list[object]]) -> list[list[object]]:
    """Header rows (trailing blank rows trimmed) followed directly by ``data``."""
    base = [list(r) for r in rows]
    while base and not any(c not in (None, "") for c in base[-1]):
        base.pop()
    return base + data


def _sheet(rows: list[list[object]]) -> SheetRows:
    width = max(len(r) for r in rows)
    text = tuple(
        tuple("" if c is None else str(c) for c in r) + ("",) * (width - len(r)) for r in rows
    )
    return SheetRows(FileFormat.OOXML, "Relatório", text)


def test_footer_removed_and_reported(header_example_rows: dict[str, list[list[object]]]) -> None:
    base = header_example_rows["P01.01.L01"]
    data = [
        ["N1", "900000001", "Utente 0001", "F", 40, "1984-01-01", "NOME MEDICO", "Freguesia"],
        ["N2", "900000002", "Utente 0002", "M", 50, "1974-01-01", "NOME MEDICO", "Freguesia"],
        ["Total", None, None, None, None, None, None, "2"],
    ]
    raw = parse_sheet(_sheet(_with_data(base, data)))
    assert raw.n_rows == 2
    (footer,) = raw.footer_rows
    assert footer[:8] == ("Total", "", "", "", "", "", "", "2")
    assert not any(footer[8:])
    assert raw.rows["c1"].to_list() == ["900000001", "900000002"]
    assert raw.rows["_row"].to_list()[0] == len(base) + 1  # 1-based row in the sheet


def test_total_row_with_patient_id_is_data(
    header_example_rows: dict[str, list[list[object]]],
) -> None:
    base = header_example_rows["P01.01.L01"]
    data = [["Total", "900000001", "Utente 0001", "F", 40, "1984-01-01", "MF", "Freg"]]
    raw = parse_sheet(_sheet(_with_data(base, data)))
    assert raw.n_rows == 1
    assert raw.footer_rows == ()


def test_footer_in_report_without_patient_ids(
    header_example_rows: dict[str, list[list[object]]],
) -> None:
    base = header_example_rows["P04.R06"]
    data = [
        ["A01", "DOR GENERALIZADA", None, 12, 1],
        ["Total", None, None, 23149, "67.830"],
    ]
    raw = parse_sheet(_sheet(_with_data(base, data)))
    assert raw.n_rows == 1
    assert len(raw.footer_rows) == 1


def test_data_stops_at_first_blank_row(
    header_example_rows: dict[str, list[list[object]]],
) -> None:
    base = header_example_rows["P10.01.L01"]
    data: list[list[object]] = [
        ["N1", "900000001", "Utente 0001", "F", 40, "Freg", "MF", "2024-05-01", "70"],
        [],
        ["nota solta", "não é dado"],
    ]
    raw = parse_sheet(_sheet(_with_data(base, data)))
    assert raw.n_rows == 1


def test_sheet_without_filter_is_rejected() -> None:
    with pytest.raises(HeaderParseError):
        parse_sheet(_sheet([["P01.01.L01. Inscritos > Utente"], ["NOP", "Utente"]]))
