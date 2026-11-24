"""User settings store and the log redaction filter."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mimufs.logging_setup import RedactFilter, setup_logging
from mimufs.settings import Settings, SettingsStore


def test_defaults_when_missing(tmp_path: Path) -> None:
    settings = SettingsStore(tmp_path / "settings.json").load()
    assert settings == Settings()
    assert settings.update_check is True
    assert settings.theme == "system"


def test_roundtrip_and_atomic_write(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "cfg" / "settings.json")
    store.update(doctor_name="Ana Sousa", theme="dark")
    assert store.load().doctor_name == "Ana Sousa"
    assert store.load().theme == "dark"
    assert [p.name for p in (tmp_path / "cfg").iterdir()] == ["settings.json"]  # no temp left


def test_corrupt_file_kept_aside_and_reset(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert SettingsStore(path).load() == Settings()
    assert not path.exists()
    assert len(list(tmp_path.glob("settings.json.corrupt-*"))) == 1


def test_unknown_keys_from_newer_versions_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "light", "future_option": 1}', encoding="utf-8")
    assert SettingsStore(path).load().theme == "light"


def test_invalid_values_rejected(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    with pytest.raises(ValueError, match="theme"):
        store.update(theme="neon")


def test_sns_numbers_never_reach_the_log(tmp_path: Path) -> None:
    setup_logging(tmp_path, console=False)
    try:
        log = logging.getLogger("mimufs.test")
        log.warning("utente %s sem médico", "123456789")
        log.warning("linha com 5550001112 (10 dígitos) fica")
        try:
            raise ValueError("could not convert '987654321'")
        except ValueError:
            log.exception("falhou a leitura")
        for handler in logging.getLogger().handlers:
            handler.flush()
        text = (tmp_path / "app.log").read_text(encoding="utf-8")
    finally:
        setup_logging(None, console=False)
    assert "123456789" not in text
    assert "987654321" not in text
    assert "utente <sns> sem médico" in text
    assert "5550001112" in text
    assert "falhou a leitura [ValueError]" in text


def test_redact_filter_on_plain_record() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "id=%s", ("900000001",), None)
    RedactFilter().filter(record)
    assert record.getMessage() == "id=<sns>"
