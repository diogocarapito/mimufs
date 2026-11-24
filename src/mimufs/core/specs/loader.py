"""Load and validate the bundled report specs and ICPC batches.

Specs are package data, read through :mod:`importlib.resources` so they work the same from
source, from a wheel and from a Briefcase bundle (never paths relative to the working dir).
"""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from importlib.resources.abc import Traversable

import yaml
from pydantic import TypeAdapter

from mimufs.core.specs.models import IcpcBatches, MimufReportSpec, ReportSpec

_SPEC_ADAPTER: TypeAdapter[ReportSpec] = TypeAdapter(ReportSpec)


class SpecError(ValueError):
    """A spec file is invalid or inconsistent."""


def reports_dir() -> Traversable:
    return files("mimufs.core") / "specs" / "reports"


def reference_dir() -> Traversable:
    return files("mimufs.core") / "reference"


def parse_spec(text: str, *, source: str = "<string>") -> ReportSpec:
    """Validate one spec from YAML text."""
    try:
        data = yaml.safe_load(text)
        return _SPEC_ADAPTER.validate_python(data)
    except Exception as exc:  # yaml.YAMLError | pydantic.ValidationError
        raise SpecError(f"{source}: {exc}") from exc


@cache
def load_specs() -> dict[str, ReportSpec]:
    """All report specs, keyed by code, in file-name order. Cached."""
    specs: dict[str, ReportSpec] = {}
    entries = sorted(
        (e for e in reports_dir().iterdir() if e.name.endswith(".yaml")), key=lambda e: e.name
    )
    for entry in entries:
        spec = parse_spec(entry.read_text(encoding="utf-8"), source=entry.name)
        if entry.name != f"{spec.code}.yaml":
            raise SpecError(f"{entry.name}: file name does not match code {spec.code!r}")
        if spec.code in specs:
            raise SpecError(f"{entry.name}: duplicate code {spec.code!r}")
        specs[spec.code] = spec
    if not specs:
        raise SpecError("no report specs found")
    return specs


def mimuf_specs() -> dict[str, MimufReportSpec]:
    """Only the MIM@UF (Excel) report specs."""
    return {code: s for code, s in load_specs().items() if isinstance(s, MimufReportSpec)}


@cache
def load_icpc_batches(name: str = "icpc_mimuf_batches.json") -> IcpcBatches:
    """The ICPC code sets the user pastes into MIM@UF (P04.01.L01)."""
    entry = reference_dir() / name
    try:
        return IcpcBatches.model_validate(json.loads(entry.read_text(encoding="utf-8")))
    except Exception as exc:
        raise SpecError(f"{name}: {exc}") from exc
