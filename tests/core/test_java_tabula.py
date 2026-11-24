"""Java runtime discovery, tabula smoke test and the SClínico reader contract."""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import pytest

from mimufs.core.readers import java_runtime, sclinico_pdf, tabula_runner
from mimufs.selftest_pdf import make_table_pdf

HEADER = ["Data", "Utente", "NOP", "Profissional", "Tipo de consulta"]
ROWS = [
    [f"2024-01-{d:02d}", f"9000000{d:02d}", f"N{d}", "Médico Teste", f"Tipo {d % 3}"]
    for d in range(1, 31)
]

needs_java = pytest.mark.skipif(
    java_runtime.find_java() is None, reason="no Java runtime on this machine"
)


@pytest.fixture
def fresh_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    java_runtime.reset()
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.setenv("JAVA_HOME", os.environ.get("JAVA_HOME", ""))
    yield
    java_runtime.reset()


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell script as fake java")
def test_bundled_jre_wins_and_goes_first_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fresh_runtime: None
) -> None:
    home = tmp_path / "jre"
    (home / "bin").mkdir(parents=True)
    fake = home / "bin" / "java"
    fake.write_text("#!/bin/sh\necho 'openjdk version \"21.0.0\" fake' >&2\n")
    fake.chmod(0o755)
    monkeypatch.setattr(java_runtime, "bundled_home", lambda: home)
    runtime = java_runtime.configure()
    assert runtime.bundled
    assert runtime.version == 'openjdk version "21.0.0" fake'
    assert os.environ["PATH"].split(os.pathsep)[0] == str(home / "bin")
    assert os.environ["JAVA_HOME"] == str(home)
    assert java_runtime.configure() is runtime  # idempotent


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell script as fake java")
def test_broken_bundled_jre_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fresh_runtime: None
) -> None:
    home = tmp_path / "jre"
    (home / "bin").mkdir(parents=True)
    fake = home / "bin" / "java"
    fake.write_text("#!/bin/sh\nexit 1\n")  # e.g. blocked by antivirus
    fake.chmod(0o755)
    monkeypatch.setattr(java_runtime, "bundled_home", lambda: home)
    with pytest.raises(java_runtime.JavaUnavailableError):
        java_runtime.configure()


@pytest.mark.requires_java
@needs_java
@pytest.mark.parametrize("mode", [{"lattice": True}, {"stream": True}])
def test_tabula_reads_synthetic_pdf(tmp_path: Path, mode: dict[str, bool]) -> None:
    pdf = tmp_path / "consultas.pdf"
    pdf.write_bytes(make_table_pdf(HEADER, ROWS, rows_per_page=12))
    tables = tabula_runner.read_pdf_tables(pdf, pandas_options={"dtype": str}, **mode)
    assert [t.shape for t in tables] == [(12, 5), (12, 5), (6, 5)]
    assert list(tables[0].columns) == HEADER
    assert tables[0].iloc[0].tolist() == ROWS[0]
    assert tables[2].iloc[-1]["Profissional"] == "Médico Teste"  # accents survive


@pytest.mark.requires_java
@needs_java
def test_tabula_error_does_not_leak_contents(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4\nnot really a pdf 900000001")
    with pytest.raises(tabula_runner.TabulaError) as info:
        tabula_runner.read_pdf_tables(bad)
    assert "900000001" not in str(info.value)


# --------------------------------------------------------------------------- SClínico CSV


def _csv(tmp_path: Path, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / "consultas.csv"
    path.write_bytes(text.encode(encoding))
    return path


def test_csv_fallback_semicolon_cp1252(tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        "Data Consulta;Utente;NOP;Profissional;Tipo Consulta;Local\n"
        "15/03/2024;900000001;N1;Médico Teste;Domicílio;Sede\n"
        "2024-03-16;900000002;N2;Médico Teste;Programada;\n",
        "cp1252",
    )
    frame = sclinico_pdf.read_appointments(path)
    assert frame.columns == list(sclinico_pdf.OUTPUT_COLUMNS)
    assert frame["data_consulta"].to_list() == [dt.date(2024, 3, 15), dt.date(2024, 3, 16)]
    assert frame["tipo_consulta"].to_list() == ["Domicílio", "Programada"]
    assert frame["local"].to_list() == ["Sede", None]


def test_csv_fallback_without_optional_local(tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        "data_consulta,utente,nop,profissional,tipo_consulta\n"
        "2024-01-02,900000001,N1,X,Programada\n",
    )
    assert sclinico_pdf.read_appointments(path)["local"].to_list() == [None]


def test_csv_missing_required_columns(tmp_path: Path) -> None:
    path = _csv(tmp_path, "data_consulta,utente\n2024-01-02,900000001\n")
    with pytest.raises(sclinico_pdf.SclinicoReadError) as info:
        sclinico_pdf.read_appointments(path)
    assert info.value.reason == "missing_columns"
    assert "tipo_consulta" in info.value.detail


@pytest.mark.needs_input
@pytest.mark.xfail(strict=True, reason="Needs Diogo's tabula.read_pdf call and cleanup")
def test_sclinico_pdf_reader(tmp_path: Path) -> None:
    pdf = tmp_path / "consultas.pdf"
    pdf.write_bytes(make_table_pdf(HEADER, ROWS))
    frame = sclinico_pdf.read_appointments(pdf)
    assert frame.height == len(ROWS)


@pytest.mark.requires_java
@needs_java
def test_accents_survive_a_non_utf8_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows' Java prints to stdout in the console code page (cp1252) unless told otherwise.

    JAVA_TOOL_OPTIONS reproduces that default on any OS; tabula_runner's own options win.
    """
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-Dstdout.encoding=windows-1252")
    pdf = tmp_path / "consultas.pdf"
    pdf.write_bytes(make_table_pdf(HEADER, ROWS, rows_per_page=40))
    (table,) = tabula_runner.read_pdf_tables(pdf, lattice=True, pandas_options={"dtype": str})
    assert table.iloc[0]["Profissional"] == "Médico Teste"
