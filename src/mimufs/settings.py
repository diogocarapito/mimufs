"""User settings: one JSON file in the platform's config directory (TECH_SPECS §7.3, §13).

Settings are personal (not per project): the doctor name pre-filled in new projects, the update
check, the theme, recent projects. Writes are atomic (temp file + ``os.replace``), so a crash
never leaves a half-written file. A corrupt file is kept aside and replaced by defaults.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import BaseModel, ConfigDict, Field, ValidationError

APP_NAME = "mimufs"
log = logging.getLogger(__name__)


class RecentProject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str  # the .mimufs file
    name: str = ""  # "USF Exemplo · 2024"
    doctor: str = ""
    description: str = ""
    progress: str = ""  # "Passo 02 · 9/18 relatórios"
    last_opened: datetime | None = None


MAX_RECENT = 10


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    doctor_name: str = ""
    update_check: bool = True
    ignored_version: str | None = None
    last_check: datetime | None = None
    theme: Literal["system", "dark", "light"] = "system"
    recent_projects: list[RecentProject] = Field(default_factory=list)
    splitter_sizes: dict[str, list[int]] = Field(default_factory=dict)


def config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False))


def data_dir() -> Path:
    """Per-user data: personal mappings and user-edited dictionaries."""
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def log_dir() -> Path:
    return Path(platformdirs.user_log_dir(APP_NAME, appauthor=False))


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "settings.json"

    def load(self) -> Settings:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Settings()
        except OSError:
            log.exception("cannot read settings; using defaults")
            return Settings()
        try:
            return Settings.model_validate(json.loads(text))
        except (ValueError, ValidationError):
            backup = self.path.with_name(f"{self.path.name}.corrupt-{datetime.now():%Y%m%d-%H%M%S}")
            log.warning("settings file is corrupt; kept as %s and reset", backup.name)
            with contextlib.suppress(OSError):
                self.path.replace(backup)
            return Settings()

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = settings.model_dump_json(indent=2)
        fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def remember_project(self, entry: RecentProject) -> Settings:
        """Put a project first in the recent list (one entry per file, at most MAX_RECENT)."""
        settings = self.load()
        others = [r for r in settings.recent_projects if r.path != entry.path]
        settings.recent_projects = [entry, *others][:MAX_RECENT]
        self.save(settings)
        return settings

    def forget_project(self, path: str) -> Settings:
        settings = self.load()
        settings.recent_projects = [r for r in settings.recent_projects if r.path != path]
        self.save(settings)
        return settings

    def update(self, **changes: object) -> Settings:
        settings = self.load()
        for key, value in changes.items():
            setattr(settings, key, value)
        self.save(settings)
        return settings
