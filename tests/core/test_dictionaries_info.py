"""Dictionaries (TECH_SPECS §10.2) and the report info card (PRD §6.3.3)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from mimufs.core.dictionaries import Dictionaries, DictionaryError, normalise
from mimufs.core.project import Project, ProjectInfo
from mimufs.core.validation.info import build_card, number
from tests.fixtures import make_fixtures as mf
from tests.fixtures.broken import Scenario

# ------------------------------------------------------------------------- dictionaries


def test_bundled_dictionaries() -> None:
    d = Dictionaries(None)
    info = {i.key: i for i in d.info()}
    assert {k: i.rows for k, i in info.items()} == {
        "medicamentos": 75,
        "icpc2": 726,
        "indicadores": 173,
    }
    assert info["medicamentos"].user_editable
    assert not info["icpc2"].user_editable
    assert d.verify_bundled() == []


def test_medication_edits_live_in_the_user_folder(tmp_path: Path) -> None:
    d = Dictionaries(tmp_path)
    table = d.table("medicamentos")
    edited = pl.concat(
        [
            table,
            pl.DataFrame(
                {
                    "medicamento": ["tirzepatido"],
                    "grupo": ["analogo de GLP-1"],
                    "doenca": ["diabetes"],
                }
            ),
        ]
    )
    d.save_medication(edited)
    assert d.medication_edited()
    assert d.table("medicamentos").height == 76
    assert {i.key: i.edited for i in d.info()}["medicamentos"]
    assert d.classify_medication(["MOUNJARO (tirzepatido) 5 mg"])[
        "MOUNJARO (tirzepatido) 5 mg"
    ] == [("tirzepatido", "analogo de GLP-1", "diabetes")]
    d.reset_medication()
    assert not d.medication_edited()
    assert d.table("medicamentos").height == 75


def test_medication_import_and_validation(tmp_path: Path) -> None:
    d = Dictionaries(tmp_path / "user")
    good = tmp_path / "meds.csv"
    row = "xigduo;biguanida;diabetes"
    good.write_bytes(f"medicamento;grupo;doenca\n{row}\n ; ;\n{row}\n".encode("cp1252"))
    assert d.import_medication(good).rows() == [("xigduo", "biguanida", "diabetes")]
    bad = tmp_path / "bad.csv"
    bad.write_text("nome,classe\nx,y\n", encoding="utf-8")
    with pytest.raises(DictionaryError, match="colunas"):
        d.import_medication(bad)
    with pytest.raises(DictionaryError, match="pasta"):
        Dictionaries(None).save_medication(d.table("medicamentos"))


def test_medication_matching_whole_words_and_combinations() -> None:
    d = Dictionaries(None)
    result = d.classify_medication(
        ["XIGDUO XR 5 mg + 1000 mg", "Metformina Generis 1000", "paracetamol"]
    )
    assert {g for _, g, _ in result["XIGDUO XR 5 mg + 1000 mg"]} == {
        "biguanida",
        "inibidor de SGLT2",
    }
    assert result["paracetamol"] == []
    assert normalise("Insulina  Glárgina-U300") == "insulina glargina u300"


def test_icpc_names() -> None:
    d = Dictionaries(None)
    assert d.icpc_name("T90") == "Diabetes não insulino-dependente"
    assert d.icpc_name("A44") == "Vacinação/medicação preventiva (A)"  # chapter + process code
    assert d.icpc_name("Z99X") == "Z99X"


# --------------------------------------------------------------------------- info card


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project.create(
        tmp_path / "p", ProjectInfo(unit=mf.UNIT, doctor=mf.PROJECT_DOCTOR, years=(mf.YEAR,))
    )


def test_card_of_a_multi_file_report(
    project: Project, synthetic_fixtures: dict[str, mf.Fixture]
) -> None:
    project.import_paths(
        [
            f.path
            for f in synthetic_fixtures.values()
            if f.kind == "valid" and f.code == "P10.01.L01"
        ]
    )
    card = build_card(project, project.report_state("P10.01.L01"))
    rows = dict(card.rows)
    assert card.subtitle == "MIM@UF · nível utente"
    assert rows["Estado"] == "Válido"
    assert rows["Unidade"] == mf.UNIT
    assert rows["Ficheiros"].startswith("5 · ")
    assert "Peso" in rows["Linhas"]
    assert "PAs" in rows["Linhas"]
    assert rows["Sem nº SNS"] == "nenhuma"
    assert "sem título → Nome" in rows["Colunas"]
    assert "Tipo Dado: " in rows["Filtros"]
    md = card.markdown()
    assert md.startswith("### P10.01.L01 · Resultados Biométricos > Utente")
    assert "900" not in md  # no patient values in the summary


def test_card_coverage_footer_and_icpc(
    project: Project,
    broken_scenarios: dict[str, Scenario],
    synthetic_fixtures: dict[str, mf.Fixture],
) -> None:
    project.import_paths(list(broken_scenarios["S01_coverage_gap"].files))
    rows = dict(build_card(project, project.report_state("P06.01.01.L03")).rows)
    assert "sem dados: Jul 2024, Ago 2024, Set 2024" in rows["Período"]
    assert rows["Estado"].startswith("Incompleto")
    project.import_paths(list(broken_scenarios["V12_footer"].files))
    assert (
        "removido" in dict(build_card(project, project.report_state("P01.01.L03")).rows)["Rodapé"]
    )
    project.import_paths(list(broken_scenarios["S02_missing_set"].files))
    assert (
        dict(build_card(project, project.report_state("P04.01.L01")).rows)["Códigos ICPC"]
        == "456/688"
    )


def test_card_of_a_pending_report(project: Project) -> None:
    rows = dict(build_card(project, project.report_state("P01.01.L01")).rows)
    assert rows == {"Estado": "Por importar", "Ficheiros": "0"}


def test_number_format() -> None:
    assert number(23149) == "23 149"
    assert number(7) == "7"
