"""Network guard: no Python code in mimufs may reach the network, except the update check.

TECH_SPECS §12.2. :func:`install` registers a :func:`sys.addaudithook`, which cannot be removed
once installed, as the very first thing in ``__main__``. The hook vetoes (raises
:class:`NetworkBlockedError` on) every DNS lookup, connection, datagram and urllib request,
unless the code runs inside :func:`allow_update_check` **and** targets ``mimufs.com:443``.

* Loopback and AF_UNIX traffic is allowed: it never leaves the machine, and Windows builds
  ``socket.socketpair()`` from a localhost TCP connection.
* Only Python-level sockets are covered. That is why the app uses no Qt networking, why DuckDB
  extension downloads are disabled, and why the Java subprocess (tabula) is covered by the
  OS-level offline test instead (TECH_SPECS §12.3).
"""

from __future__ import annotations

import contextvars
import ipaddress
import logging
import socket
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

UPDATE_HOST = "mimufs.com"
UPDATE_PORT = 443
UPDATE_URL = f"https://{UPDATE_HOST}/version.json"
ALLOWED: frozenset[tuple[str, int]] = frozenset({(UPDATE_HOST, UPDATE_PORT)})

_EVENTS = frozenset(
    {"socket.getaddrinfo", "socket.connect", "socket.sendto", "socket.sendmsg", "urllib.Request"}
)

_updater_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "mimufs_updater_active", default=False
)
_resolved_update_ips: set[str] = set()
_lock = threading.Lock()
_installed = False
_blocked = 0
_allowed = 0

log = logging.getLogger(__name__)


class NetworkBlockedError(PermissionError):
    """A network operation was vetoed by the mimufs network guard."""


@dataclass(frozen=True)
class Stats:
    installed: bool
    blocked: int  # attempts vetoed since start-up
    allowed: int  # connections made by the update check


def install() -> None:
    """Install the audit hook (idempotent, irreversible)."""
    global _installed
    with _lock:
        if _installed:
            return
        sys.addaudithook(_hook)
        _installed = True


def is_installed() -> bool:
    return _installed


def stats() -> Stats:
    return Stats(installed=_installed, blocked=_blocked, allowed=_allowed)


@contextmanager
def allow_update_check() -> Iterator[None]:
    """Allow DNS + HTTPS to ``mimufs.com:443`` in the current context (thread/task) only."""
    token = _updater_active.set(True)
    try:
        yield
    finally:
        _updater_active.reset(token)


def resolve_update_host() -> set[str]:
    """Resolve mimufs.com inside the allowed context and remember its addresses."""
    if not _updater_active.get():
        raise NetworkBlockedError("mimufs netguard: resolve only inside allow_update_check()")
    infos = socket.getaddrinfo(UPDATE_HOST, UPDATE_PORT, type=socket.SOCK_STREAM)
    ips = {str(info[4][0]) for info in infos}
    with _lock:
        _resolved_update_ips.update(ips)
    return ips


# ------------------------------------------------------------------------------- the hook


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if event not in _EVENTS:
        return
    reason = decide(event, args, updater_active=_updater_active.get())
    if reason is None:
        return
    global _blocked
    _blocked += 1
    log.warning("netguard blocked a network operation (%s)", event)
    raise NetworkBlockedError(f"mimufs netguard: {reason}")


def decide(event: str, args: tuple[Any, ...], *, updater_active: bool) -> str | None:
    """Return why an audited operation must be blocked, or None to allow it. Pure."""
    global _allowed
    if event == "socket.getaddrinfo":
        host, port = _host_text(args[0]), _port(args[1])
        if _is_loopback_host(host):
            return None
        if updater_active and (host, port) in ALLOWED:
            return None
        return f"blocked DNS lookup for {host}"
    if event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        address = args[1] if len(args) > 1 else None
        if _is_local_address(address):
            return None
        if event == "socket.connect" and updater_active:
            ip = address[0] if isinstance(address, tuple) and address else None
            if ip in _resolved_update_ips and _port(address[1]) == UPDATE_PORT:  # type: ignore[index]
                _allowed += 1
                return None
        return "blocked connection"
    if event == "urllib.Request":
        url = str(args[0])
        if updater_active and url == UPDATE_URL:
            return None
        return "blocked urllib request"
    return None


def _host_text(host: object) -> str:
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    return str(host).lower().rstrip(".") if host is not None else ""


def _port(port: object) -> int | None:
    try:
        return int(port)  # type: ignore[call-overload,no-any-return]
    except (TypeError, ValueError):
        return {"https": 443, "http": 80}.get(str(port))


def _is_loopback_host(host: str) -> bool:
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def _is_local_address(address: object) -> bool:
    if address is None:
        return True  # sendmsg on a connected socket: the connect was already checked
    if isinstance(address, str | bytes):
        return True  # AF_UNIX path
    if isinstance(address, tuple) and address:
        return _is_loopback_host(_host_text(address[0]))
    return False
