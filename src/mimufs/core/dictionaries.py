"""Bundled reference dictionaries and the user's medication edits (TECH_SPECS §10.2, PRD §7.5).

The bundled files in ``core/reference/dictionaries/`` are read-only and checksummed. The
medication dictionary is user-editable: edits are a full copy in the user's data folder
(``<user_dir>/medicamentos.csv``), reused by every project; "Repor original" deletes the copy.
The app never downloads dictionaries.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

import polars as pl

from mimufs.core.specs.loader import reference_dir

DictKey = Literal["medicamentos", "icpc2", "indicadores"]
KEYS: tuple[DictKey, ...] = ("medicamentos", "icpc2", "indicadores")
MEDICATION_COLUMNS = ("medicamento", "grupo", "doenca")
USER_MEDICATION_FILE = "medicamentos.csv"


class DictionaryError(ValueError):
    """A dictionary file can't be used. ``str(exc)`` is PT-PT and safe to show."""


@dataclass(frozen=True)
class DictionaryInfo:
    key: DictKey
    file: str
    version: str
    sha256: str
    source: str
    source_date: str
    rows: int
    user_editable: bool
    edited: bool  # the user's copy is in use


def normalise(text: str) -> str:
    """Lower-case, no accents, punctuation → spaces (medication matching)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@cache
def manifest() -> dict[str, dict[str, object]]:
    data = (reference_dir() / "dictionaries" / "dictionaries.json").read_text(encoding="utf-8")
    loaded: dict[str, dict[str, object]] = json.loads(data)
    return loaded


def _bundled_bytes(key: DictKey) -> bytes:
    return (reference_dir() / "dictionaries" / str(manifest()[key]["file"])).read_bytes()


def _read_csv(data: bytes) -> pl.DataFrame:
    return pl.read_csv(io.BytesIO(data), infer_schema=False, encoding="utf8")


class Dictionaries:
    def __init__(self, user_dir: Path | None = None) -> None:
        self.user_dir = user_dir

    # ----------------------------------------------------------------------- reading

    @property
    def _user_medication(self) -> Path | None:
        return self.user_dir / USER_MEDICATION_FILE if self.user_dir else None

    def medication_edited(self) -> bool:
        path = self._user_medication
        return bool(path and path.is_file())

    def table(self, key: DictKey) -> pl.DataFrame:
        if key == "medicamentos" and self.medication_edited():
            assert self._user_medication is not None
            return _read_csv(self._user_medication.read_bytes())
        return _read_csv(_bundled_bytes(key))

    def info(self) -> list[DictionaryInfo]:
        out = []
        for key in KEYS:
            entry = manifest()[key]
            edited = key == "medicamentos" and self.medication_edited()
            out.append(
                DictionaryInfo(
                    key=key,
                    file=str(entry["file"]),
                    version=str(entry["version"]) + (" + edições" if edited else ""),
                    sha256=str(entry["sha256"]),
                    source=str(entry["source"]),
                    source_date=str(entry["source_date"]),
                    rows=self.table(key).height,
                    user_editable=bool(entry["user_editable"]),
                    edited=edited,
                )
            )
        return out

    def verify_bundled(self) -> list[DictKey]:
        """Keys whose bundled file no longer matches its checksum (should be empty)."""
        return [
            key
            for key in KEYS
            if hashlib.sha256(_bundled_bytes(key)).hexdigest() != manifest()[key]["sha256"]
        ]

    # --------------------------------------------------------------- medication edits

    @staticmethod
    def clean_medication(frame: pl.DataFrame) -> pl.DataFrame:
        """Validate and tidy a medication table (exact columns, no empty terms, no repeats)."""
        columns = [c.strip().lower() for c in frame.columns]
        if columns != list(MEDICATION_COLUMNS):
            raise DictionaryError(
                "O ficheiro tem de ter exatamente as colunas: medicamento, grupo, doenca."
            )
        frame = frame.rename(dict(zip(frame.columns, MEDICATION_COLUMNS, strict=True)))
        frame = frame.select(
            [
                pl.col(c).cast(pl.Utf8).fill_null("").str.strip_chars().alias(c)
                for c in MEDICATION_COLUMNS
            ]
        )
        frame = frame.filter(pl.col("medicamento") != "").unique(maintain_order=True)
        if frame.is_empty():
            raise DictionaryError("O dicionário de medicamentos não pode ficar vazio.")
        return frame

    def save_medication(self, frame: pl.DataFrame) -> pl.DataFrame:
        path = self._user_medication
        if path is None:
            raise DictionaryError("Sem pasta de dados do utilizador para guardar as edições.")
        clean = self.clean_medication(frame)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".medicamentos-", suffix=".csv", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                clean.write_csv(fh)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return clean

    def import_medication(self, source: Path) -> pl.DataFrame:
        data = source.read_bytes()
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise DictionaryError("O ficheiro não está em UTF-8 nem em Windows-1252.")
        separator = (
            ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
        )
        try:
            frame = pl.read_csv(io.StringIO(text), separator=separator, infer_schema=False)
        except Exception:
            raise DictionaryError("Não foi possível ler o ficheiro CSV.") from None
        return self.save_medication(frame)

    def export(self, key: DictKey, target: Path) -> None:
        self.table(key).write_csv(target)

    def reset_medication(self) -> None:
        """ "Repor original": drop the user's copy, back to the bundled dictionary."""
        path = self._user_medication
        if path and path.exists():
            path.unlink()

    # -------------------------------------------------------------------- lookups

    def classify_medication(self, names: Iterable[str]) -> dict[str, list[tuple[str, str, str]]]:
        """name → every (term, grupo, doenca) whose term is a whole word of the name."""
        rows = self.table("medicamentos").rows()
        terms = [(normalise(t), t, g, d) for t, g, d in rows if normalise(t)]
        out: dict[str, list[tuple[str, str, str]]] = {}
        for name in names:
            padded = f" {normalise(name)} "
            out[name] = [(t, g, d) for norm, t, g, d in terms if f" {norm} " in padded]
        return out

    def icpc_name(self, code: str, *, short: bool = False) -> str:
        """Readable ICPC name; chapter + process codes (A44…) get a derived name."""
        names = _icpc_names(short)
        if code in names:
            return names[code]
        match = re.fullmatch(r"([A-Z])(\d{2})", code)
        if match and f"-{match[2]}" in names:
            return f"{names['-' + match[2]]} ({match[1]})"
        return code


@cache
def _icpc_names(short: bool) -> dict[str, str]:
    frame = _read_csv(_bundled_bytes("icpc2"))
    column = "nome_curto" if short else "nome"
    return dict(zip(frame["cod"].to_list(), frame[column].to_list(), strict=True))
