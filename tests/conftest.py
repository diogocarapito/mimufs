from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.fixtures import make_fixtures

# Qt widget tests never need a display (CI runners have none on Linux).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def header_example_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Each sheet of docs/reference/MIMUF_Header_examples.xlsx as its own .xls file."""
    return make_fixtures.split_header_examples(tmp_path_factory.mktemp("headers"))


@pytest.fixture(scope="session")
def header_example_rows() -> dict[str, list[list[object]]]:
    return make_fixtures.header_example_rows()


@pytest.fixture(scope="session")
def synthetic_fixtures(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, make_fixtures.Fixture]:
    """Every synthetic fixture (valid files per slot, variants, SClínico), generated once."""
    return make_fixtures.generate(tmp_path_factory.mktemp("synthetic"))
