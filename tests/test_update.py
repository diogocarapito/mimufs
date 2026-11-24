"""Update notifier (TECH_SPECS §13). No network: the opener is replaced."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mimufs import __version__, netguard, update
from mimufs.settings import SettingsStore

DOC = {
    "latest": "0.2.0",
    "released": "2027-01-15",
    "min_supported": "0.0.1",
    "download_url": "https://mimufs.com/#download",
    "notes_pt": ["Novo relatório P05.01.L02", "Correção na validação de trimestres"],
}


def fetcher(doc: object = DOC):  # type: ignore[no-untyped-def]
    def fetch() -> update.VersionDoc:
        return update.fetch_version_doc(opener=lambda req, timeout: json.dumps(doc).encode())

    return fetch


def test_newer_version_detected() -> None:
    info = update.check("0.1.0", None, fetcher())
    assert info is not None
    assert (info.latest, info.supported) == ("0.2.0", True)
    assert info.notes_pt[0] == "Novo relatório P05.01.L02"


@pytest.mark.parametrize(
    ("current", "ignored"), [("0.2.0", None), ("0.3.0", None), ("0.1.0", "0.2.0")]
)
def test_no_update(current: str, ignored: str | None) -> None:
    assert update.check(current, ignored, fetcher()) is None


def test_unsupported_old_version_flagged() -> None:
    info = update.check("0.0.1", None, fetcher({**DOC, "min_supported": "0.1.0"}))
    assert info is not None
    assert info.supported is False


@pytest.mark.parametrize(
    "doc",
    [
        {"released": "2027-01-15"},  # no latest
        {**DOC, "latest": "not-a-version"},
        {**DOC, "download_url": "https://evil.example/mimufs.exe"},
        {**DOC, "download_url": "http://mimufs.com/#download"},
    ],
)
def test_bad_documents_fail_silently(doc: object) -> None:
    assert update.check("0.1.0", None, fetcher(doc)) is None


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("offline"),
        TimeoutError(),
        netguard.NetworkBlockedError("blocked"),
        ValueError("too large"),
    ],
)
def test_network_failures_fail_silently(error: Exception) -> None:
    def fetch() -> update.VersionDoc:
        raise error

    assert update.check("0.1.0", None, fetch) is None


def test_bad_json_fails_silently() -> None:
    def fetch() -> update.VersionDoc:
        return update.fetch_version_doc(opener=lambda req, timeout: b"<html>")

    assert update.check("0.1.0", None, fetch) is None


def test_request_carries_only_the_user_agent() -> None:
    request = update.build_request()
    assert request.full_url == "https://mimufs.com/version.json"
    assert request.get_method() == "GET"
    assert request.header_items() == [("User-agent", f"mimufs/{__version__}")]


def test_fetch_runs_inside_the_allowed_context() -> None:
    seen: list[bool] = []

    def opener(req: urllib.request.Request, timeout: float) -> bytes:
        seen.append(netguard._updater_active.get())
        assert timeout == update.TIMEOUT_S
        return json.dumps(DOC).encode()

    update.fetch_version_doc(opener=opener)
    assert seen == [True]
    assert netguard._updater_active.get() is False


def test_startup_check_throttled_and_switchable(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    calls: list[int] = []

    def fetch() -> update.VersionDoc:
        calls.append(1)
        return update.VersionDoc.model_validate({**DOC, "latest": "99.0.0"})

    now = datetime(2026, 11, 24, 10, tzinfo=UTC)
    assert update.startup_check(store, now, fetch) is not None
    assert update.startup_check(store, now + timedelta(hours=23), fetch) is None
    assert update.startup_check(store, now + timedelta(hours=25), fetch) is not None
    assert len(calls) == 2
    store.update(update_check=False)
    assert update.startup_check(store, now + timedelta(days=9), fetch) is None
    assert len(calls) == 2
