"""What the checks need to know about the project."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def norm_text(value: str) -> str:
    """Compare names the way a person would: case, accents and spacing don't matter."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value).strip().casefold()


@dataclass(frozen=True)
class ProjectCtx:
    unit: str  # exactly as in MIM@UF ("Unidade Funcional")
    doctor: str  # as in MIM@UF ("NOME: M 00000"); may be empty
    years: tuple[int, ...]  # 1 or 2 project years

    def __post_init__(self) -> None:
        if not self.years or len(self.years) > 2:
            raise ValueError("a project has 1 or 2 years")

    def same_unit(self, found: str) -> bool:
        return norm_text(found) == norm_text(self.unit)

    def is_project_doctor(self, found: str) -> bool:
        if not self.doctor:
            return False
        a, b = norm_text(found), norm_text(self.doctor)
        # "NOME MEDICO: M 00001" vs "Nome Medico": the name part is enough.
        return a == b or a.split(":")[0].strip() == b.split(":")[0].strip()
