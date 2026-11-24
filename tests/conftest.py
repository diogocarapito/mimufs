from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures import make_fixtures


@pytest.fixture(scope="session")
def header_example_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Each sheet of docs/reference/MIMUF_Header_examples.xlsx as its own .xls file."""
    return make_fixtures.split_header_examples(tmp_path_factory.mktemp("headers"))


@pytest.fixture(scope="session")
def header_example_rows() -> dict[str, list[list[object]]]:
    return make_fixtures.header_example_rows()
