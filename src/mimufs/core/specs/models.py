"""Pydantic models for the report specs (TECH_SPECS §6).

The YAML files in ``core/specs/reports/`` are the source of truth for what each MIM@UF export
(or the SClínico appointments list) looks like. These models validate them at start-up and in CI.
Every model forbids unknown keys, so a typo in a spec fails loudly instead of being ignored.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ColumnType = Literal["str", "cat", "int", "float", "date", "ignore"]
Role = Literal[
    "sns", "nop", "doctor", "unit", "icpc", "medication", "exam", "indicator", "prescriber",
    "period",
]  # fmt: skip
Level = Literal["patient", "patient_event", "doctor", "unit", "family"]
Month = Annotated[int, Field(ge=1, le=12)]

MIMUF_CODE_RE = re.compile(r"^P\d{2}(?:\.\d{2}){0,2}\.[LR]\d{2}$")
SCLINICO_CODE_RE = re.compile(r"^SCLINICO\.[a-z_]+$")
SLOT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Placeholders allowed in instructions and ``filter_expect`` values.
PLACEHOLDERS = ("{ano}", "{unidade}")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _normalise_cell(value: str) -> str:
    """Whitespace-normalise a header cell the way the specs were generated."""
    return re.sub(r"\s+", " ", value).strip()


class Column(_Model):
    """One column of a MIM@UF export, matched by position."""

    at: int = Field(ge=0, description="0-based column index in the file")
    header: str = Field(description="Exact header text in the file; '' = untitled cell")
    name: str = Field(min_length=1, description="Canonical column name")
    type: ColumnType
    role: Role | None = None
    required: bool = False
    pii: bool = False
    drop: bool = Field(False, description="Removed at import, never stored (data minimisation)")
    export_default: bool = True
    row2: bool = Field(False, description="The header text lives in the second header row")
    match: Literal["exact", "startswith"] = "exact"
    parse: Literal["decimal_pt"] | None = None

    def matches(self, cell: str) -> bool:
        """Whether a (whitespace-normalised) header cell matches this column."""
        got = _normalise_cell(cell)
        if self.match == "startswith":
            return got.startswith(self.header)
        return got == self.header


class Header(_Model):
    rows: Literal[1, 2] = 1
    columns: tuple[Column, ...] = Field(min_length=1)
    note: str | None = None

    @field_validator("columns")
    @classmethod
    def _sorted_unique(cls, columns: tuple[Column, ...]) -> tuple[Column, ...]:
        positions = [c.at for c in columns]
        if len(set(positions)) != len(positions):
            raise ValueError(f"duplicate column positions: {positions}")
        names = [c.name for c in columns]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate column names: {names}")
        return tuple(sorted(columns, key=lambda c: c.at))

    @model_validator(mode="after")
    def _row2_needs_two_rows(self) -> Header:
        if self.rows == 1 and any(c.row2 for c in self.columns):
            raise ValueError("'row2' columns need header.rows = 2")
        return self

    @property
    def width(self) -> int:
        return self.columns[-1].at + 1

    def by_role(self, *roles: Role) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.role in roles)


# ----------------------------------------------------------------------------------- slots


class _SlotsBase(_Model):
    note: str | None = None


def _unique_months(months: tuple[int, ...]) -> tuple[int, ...]:
    if len(set(months)) != len(months):
        raise ValueError(f"duplicate months: {months}")
    return tuple(sorted(months))


class MonthsSlots(_SlotsBase):
    """One file per listed month (``YYYY-MM`` from the effective ``Mês``)."""

    kind: Literal["months"]
    months: tuple[Month, ...] = Field(min_length=1)

    _check_months = field_validator("months")(_unique_months)


class MonthCoverageSlots(_SlotsBase):
    """Files by quarter or month (or one file listing months) that together cover the year."""

    kind: Literal["month_coverage"]
    months: tuple[Month, ...] = Field(min_length=1)
    display: Literal["months", "quarters"] = "months"

    _check_months = field_validator("months")(_unique_months)


class YearSlots(_SlotsBase):
    """One file for the project year."""

    kind: Literal["year"]


class ValuesSlots(_SlotsBase):
    """One file per value of a filter field (e.g. ``Tipo Dado``); slot id -> regex."""

    kind: Literal["values"]
    key: str = Field(pattern=r"^filter\..+")
    months: tuple[Month, ...] = Field(min_length=1)
    values: dict[str, str] = Field(min_length=1)

    _check_months = field_validator("months")(_unique_months)

    @field_validator("values")
    @classmethod
    def _valid_patterns(cls, values: dict[str, str]) -> dict[str, str]:
        for slot_id, pattern in values.items():
            if not SLOT_ID_RE.match(slot_id):
                raise ValueError(f"slot id {slot_id!r} must be snake_case")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"slot {slot_id!r}: invalid regex {pattern!r}: {exc}") from exc
        return values

    @property
    def filter_key(self) -> str:
        return self.key.removeprefix("filter.")

    def match(self, value: str) -> list[str]:
        """Slot ids whose pattern matches ``value`` (normally exactly one)."""
        return [slot for slot, pattern in self.values.items() if re.search(pattern, value)]


class IcpcSetsSlots(_SlotsBase):
    """P04.01.L01: one file per ICPC code set (``core/reference/<sets_file>``)."""

    kind: Literal["icpc_sets"]
    sets_file: str
    months: tuple[Month, ...] = Field(min_length=1)

    _check_months = field_validator("months")(_unique_months)


Slots = Annotated[
    MonthsSlots | MonthCoverageSlots | YearSlots | ValuesSlots | IcpcSetsSlots,
    Field(discriminator="kind"),
]


# ----------------------------------------------------------------------------------- specs


class _SpecBase(_Model):
    code: str
    title: str = Field(min_length=1)
    group: str = Field(min_length=1, description="Section of the report checklist (PT-PT)")
    level: Level
    required: bool
    purpose: str = Field(min_length=1, description="PT-PT, one line")
    instructions: tuple[str, ...] = Field(min_length=1, description="PT-PT steps")
    slots: Slots

    def render_instructions(self, *, ano: int | str, unidade: str) -> list[str]:
        """Instructions with ``{ano}`` and ``{unidade}`` filled in (other braces untouched)."""
        return [
            line.replace("{ano}", str(ano)).replace("{unidade}", unidade)
            for line in self.instructions
        ]


class MimufReportSpec(_SpecBase):
    source: Literal["mimuf"]
    header: Header
    pages_expect: dict[str, str] = Field(default_factory=dict)
    filter_expect: dict[str, str] = Field(default_factory=dict)
    doctor_pages: tuple[str, ...] = ()
    doctor_pages_default: Literal["total_or_project_doctor"] = "total_or_project_doctor"
    no_pages: bool = False

    @field_validator("code")
    @classmethod
    def _code_format(cls, code: str) -> str:
        if not MIMUF_CODE_RE.match(code):
            raise ValueError(f"not a MIM@UF report code: {code!r}")
        return code

    @property
    def id_columns(self) -> tuple[Column, ...]:
        """Patient-ID columns (SNS number and NOP)."""
        return self.header.by_role("sns", "nop")


class SclinicoReportSpec(_SpecBase):
    source: Literal["sclinico_pdf"]
    output_contract: tuple[str, ...] = Field(min_length=1)
    todo: str | None = None

    @field_validator("code")
    @classmethod
    def _code_format(cls, code: str) -> str:
        if not SCLINICO_CODE_RE.match(code):
            raise ValueError(f"not a SClínico report code: {code!r}")
        return code


ReportSpec = Annotated[MimufReportSpec | SclinicoReportSpec, Field(discriminator="source")]


# ----------------------------------------------------------------------------- ICPC batches


class IcpcBatch(_Model):
    n: int = Field(ge=1)
    first: str
    last: str
    entries: int
    unique: int
    codes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> IcpcBatch:
        if len(self.codes) != self.entries or len(set(self.codes)) != self.unique:
            raise ValueError(f"batch {self.n}: entries/unique do not match its codes")
        if (self.codes[0], self.codes[-1]) != (self.first, self.last):
            raise ValueError(f"batch {self.n}: first/last do not match its codes")
        return self

    def paste_text(self, separator: str = ", ") -> str:
        """The text the user pastes into the MIM@UF ICPC filter."""
        return separator.join(self.codes)


class IcpcBatches(_Model):
    source: str
    paste_separator: str
    paste_format: Literal["code_only"]
    note: str | None = None
    batches: tuple[IcpcBatch, ...] = Field(min_length=1)
    target_unique: tuple[str, ...]
    target_count: int

    @model_validator(mode="after")
    def _target_matches(self) -> IcpcBatches:
        if len(self.target_unique) != self.target_count:
            raise ValueError("target_count does not match target_unique")
        union = {code for batch in self.batches for code in batch.codes}
        if union != set(self.target_unique):
            raise ValueError("the union of the batches is not the target list")
        return self

    @property
    def target(self) -> frozenset[str]:
        return frozenset(self.target_unique)
