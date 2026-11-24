"""Update notifier: the one network request mimufs ever makes (TECH_SPECS §13, PRD §7.2).

``GET https://mimufs.com/version.json`` with a 5 s timeout, the operating system's certificate
store (``truststore``: SPMS networks inspect HTTPS with their own root certificate), no proxy,
no cookies, and no header that identifies the user: only ``User-Agent: mimufs/<version>``.
Any failure is silent (logged locally) and the user can always download from the website.
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import truststore
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from mimufs import __version__, netguard
from mimufs.settings import Settings, SettingsStore

UPDATE_URL = netguard.UPDATE_URL
TIMEOUT_S = 5.0
CHECK_INTERVAL = timedelta(hours=24)
MAX_BYTES = 64 * 1024
ALLOWED_DOWNLOAD_PREFIXES = ("https://mimufs.com/", "https://github.com/diogocarapito/mimufs/")

log = logging.getLogger(__name__)


class VersionDoc(BaseModel):
    """``site/version.json``."""

    model_config = ConfigDict(extra="ignore")

    latest: str
    released: str | None = None
    min_supported: str | None = None
    download_url: str = "https://mimufs.com/#download"
    notes_pt: list[str] = Field(default_factory=list)

    @field_validator("latest", "min_supported")
    @classmethod
    def _valid_version(cls, value: str | None) -> str | None:
        if value is not None:
            Version(value)  # raises InvalidVersion (a ValueError)
        return value

    @field_validator("download_url")
    @classmethod
    def _trusted_url(cls, value: str) -> str:
        # Never open an arbitrary URL from the network, even if the site were compromised.
        if not value.startswith(ALLOWED_DOWNLOAD_PREFIXES):
            raise ValueError("download_url is not on mimufs.com or the GitHub repo")
        return value


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    latest: str
    released: str | None
    download_url: str
    notes_pt: tuple[str, ...]
    supported: bool  # False when current < min_supported


def build_request() -> urllib.request.Request:
    return urllib.request.Request(
        UPDATE_URL, headers={"User-Agent": f"mimufs/{__version__}"}, method="GET"
    )


def _open(request: urllib.request.Request, timeout: float) -> bytes:
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),  # only ever talk to mimufs.com itself
        urllib.request.HTTPSHandler(context=context),
    )
    opener.addheaders = []  # no default "Python-urllib" User-Agent or anything else
    with opener.open(request, timeout=timeout) as response:
        data: bytes = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("version.json is unexpectedly large")
    return data


def fetch_version_doc(
    timeout: float = TIMEOUT_S,
    opener: Callable[[urllib.request.Request, float], bytes] = _open,
) -> VersionDoc:
    with netguard.allow_update_check():
        if netguard.is_installed():
            netguard.resolve_update_host()
        data = opener(build_request(), timeout)
    return VersionDoc.model_validate(json.loads(data))


def evaluate(doc: VersionDoc, current: str, ignored_version: str | None) -> UpdateInfo | None:
    """An :class:`UpdateInfo` when ``doc.latest`` is newer and not ignored, else None."""
    try:
        latest, now = Version(doc.latest), Version(current)
    except InvalidVersion:
        return None
    if latest <= now or doc.latest == ignored_version:
        return None
    supported = doc.min_supported is None or now >= Version(doc.min_supported)
    return UpdateInfo(
        current=current,
        latest=doc.latest,
        released=doc.released,
        download_url=doc.download_url,
        notes_pt=tuple(doc.notes_pt),
        supported=supported,
    )


def check(
    current: str = __version__,
    ignored_version: str | None = None,
    fetch: Callable[[], VersionDoc] = fetch_version_doc,
) -> UpdateInfo | None:
    """Check now ("Verificar agora"). Never raises: offline or errors → None, logged."""
    try:
        doc = fetch()
    except (OSError, ValueError, ValidationError, ssl.SSLError) as exc:
        # OSError covers URLError, timeouts and netguard.NetworkBlockedError.
        log.info("update check failed silently (%s)", type(exc).__name__)
        return None
    return evaluate(doc, current, ignored_version)


def is_due(settings: Settings, now: datetime | None = None) -> bool:
    if not settings.update_check:
        return False
    if settings.last_check is None:
        return True
    now = now or datetime.now(UTC)
    last = settings.last_check
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return now - last >= CHECK_INTERVAL


def startup_check(
    store: SettingsStore,
    now: datetime | None = None,
    fetch: Callable[[], VersionDoc] = fetch_version_doc,
) -> UpdateInfo | None:
    """The automatic check at start-up: at most once every 24 h, only if enabled."""
    settings = store.load()
    if not is_due(settings, now):
        return None
    info = check(__version__, settings.ignored_version, fetch)
    store.update(last_check=now or datetime.now(UTC))
    return info
