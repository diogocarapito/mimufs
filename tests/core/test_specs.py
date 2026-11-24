"""Report specs, ICPC batches and dictionary manifest (TECH_SPECS §6, §6.3, §10.2)."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files

import pytest

from mimufs.core.specs import (
    MimufReportSpec,
    SclinicoReportSpec,
    SpecError,
    load_icpc_batches,
    load_specs,
    mimuf_specs,
)
from mimufs.core.specs.loader import parse_spec
from mimufs.core.specs.models import ValuesSlots

MIMUF_CODES = {
    "P01.01.L01", "P01.01.L03", "P01.01.L04", "P01.01.L06",
    "P02.01.R01", "P02.01.R03", "P02.01.R04",
    "P04.01.L01", "P04.01.L05", "P04.R06",
    "P05.01.L02", "P05.R01",
    "P06.01.01.L03", "P06.01.R02",
    "P07.01.01.L01", "P07.03.01.L01",
    "P10.01.L01",
}  # fmt: skip


def test_all_specs_load() -> None:
    specs = load_specs()
    assert set(specs) == MIMUF_CODES | {"SCLINICO.consultas"}
    assert set(mimuf_specs()) == MIMUF_CODES
    assert isinstance(specs["SCLINICO.consultas"], SclinicoReportSpec)


@pytest.mark.parametrize("code", sorted(MIMUF_CODES))
def test_mimuf_spec_invariants(code: str) -> None:
    spec = mimuf_specs()[code]
    cols = spec.header.columns
    assert [c.at for c in cols] == sorted(c.at for c in cols)
    # Untitled cells always get a real name; Métrica layout columns are ignored.
    assert all(c.name for c in cols)
    assert all(c.type == "ignore" for c in cols if c.header == "Métrica")
    # Patient-level reports carry an SNS column; family/unit/doctor reports may not.
    if spec.level in ("patient", "patient_event"):
        assert spec.header.by_role("sns"), "patient-level report without an SNS column"
    # PII never exported by default.
    assert all(not c.export_default for c in cols if c.pii)


def test_p01_01_l03_drops_contact_columns() -> None:
    spec = mimuf_specs()["P01.01.L03"]
    assert {c.name for c in spec.header.columns if c.drop} == {
        "Morada",
        "Código Postal",
        "Telefone",
    }


def test_values_slots_match_known_names() -> None:
    p10 = mimuf_specs()["P10.01.L01"].slots
    p07 = mimuf_specs()["P07.03.01.L01"].slots
    assert isinstance(p10, ValuesSlots)
    assert isinstance(p07, ValuesSlots)
    assert p10.filter_key == "Tipo Dado"
    assert p10.match("Altura(Cm)") == ["altura"]
    assert p10.match("TAd") == ["pad"]
    assert p07.match("651029:Colesterol total, s/l") == ["colesterol_total"]


def test_render_instructions_fills_placeholders() -> None:
    spec = mimuf_specs()["P01.01.L01"]
    lines = spec.render_instructions(ano=2024, unidade="USF Exemplo")
    assert any("Mês = 2024-01" in line and "USF Exemplo" in line for line in lines)
    assert not any("{ano}" in line or "{unidade}" in line for line in lines)


def _minimal_spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "code": "P99.01.L01",
        "source": "mimuf",
        "title": "Teste",
        "group": "Teste",
        "level": "patient",
        "required": True,
        "purpose": "Teste.",
        "instructions": ["Passo 1."],
        "slots": {"kind": "months", "months": [12]},
        "header": {
            "rows": 1,
            "columns": [{"at": 0, "header": "Utente", "name": "Utente", "type": "str"}],
        },
    }
    spec.update(overrides)
    return spec


def test_unknown_key_is_rejected() -> None:
    bad = json.dumps(_minimal_spec(colour="red"))
    with pytest.raises(SpecError, match="colour"):
        parse_spec(bad)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"code": "X01"}, "not a MIM@UF report code"),
        ({"slots": {"kind": "months", "months": [13]}}, "less than or equal to 12"),
        ({"slots": {"kind": "months", "months": [1, 1]}}, "duplicate months"),
        ({"slots": {"kind": "weeks"}}, "kind"),
        (
            {
                "slots": {
                    "kind": "values",
                    "key": "filter.X",
                    "months": [12],
                    "values": {"a": "(unclosed"},
                }
            },
            "invalid regex",
        ),
        (
            {
                "header": {
                    "rows": 1,
                    "columns": [
                        {"at": 0, "header": "A", "name": "A", "type": "str"},
                        {"at": 0, "header": "B", "name": "B", "type": "str"},
                    ],
                }
            },
            "duplicate column positions",
        ),
        (
            {
                "header": {
                    "rows": 1,
                    "columns": [{"at": 0, "header": "A", "name": "A", "type": "str", "row2": True}],
                }
            },
            "row2",
        ),
    ],
)
def test_invalid_specs_fail_loudly(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(SpecError, match=message):
        parse_spec(json.dumps(_minimal_spec(**overrides)))


def test_minimal_spec_is_valid() -> None:
    spec = parse_spec(json.dumps(_minimal_spec()))
    assert isinstance(spec, MimufReportSpec)
    assert spec.doctor_pages_default == "total_or_project_doctor"


# ------------------------------------------------------------------------------ ICPC batches


def test_icpc_batches_no_duplicates_no_overlap() -> None:
    batches = load_icpc_batches()
    assert [b.n for b in batches.batches] == [1, 2, 3]
    assert [len(b.codes) for b in batches.batches] == [205, 251, 232]
    seen: set[str] = set()
    for batch in batches.batches:
        assert len(set(batch.codes)) == len(batch.codes), f"duplicates in batch {batch.n}"
        assert not seen & set(batch.codes), f"batch {batch.n} overlaps an earlier batch"
        seen |= set(batch.codes)
    assert len(batches.target) == 688


def test_icpc_paste_text_format() -> None:
    first = load_icpc_batches().batches[0]
    text = first.paste_text()
    assert text.startswith("A01, A02, ")
    assert ",," not in text
    assert text.count(", ") == len(first.codes) - 1


# --------------------------------------------------------------------------- dictionaries


def test_dictionary_manifest_hashes_match() -> None:
    folder = files("mimufs.core") / "reference" / "dictionaries"
    manifest = json.loads((folder / "dictionaries.json").read_text(encoding="utf-8"))
    for name, entry in manifest.items():
        digest = hashlib.sha256((folder / entry["file"]).read_bytes()).hexdigest()
        assert digest == entry["sha256"], f"{name}: bundled file changed without a version bump"
