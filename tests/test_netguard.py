"""Network guard (TECH_SPECS §12.2). Installed in a subprocess: audit hooks can't be removed."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

from mimufs import netguard

PROBE = textwrap.dedent(
    """
    import json, socket, urllib.request
    from mimufs import netguard

    netguard.install()
    netguard.install()  # idempotent
    out = {}

    def attempt(name, fn):
        try:
            fn()
            out[name] = "allowed"
        except netguard.NetworkBlockedError:
            out[name] = "blocked"
        except OSError as exc:  # allowed by the guard, failed for another reason
            out[name] = "allowed:" + type(exc).__name__

    attempt("dns", lambda: socket.getaddrinfo("example.com", 443))
    attempt("dns_update_host_outside_context", lambda: socket.getaddrinfo("mimufs.com", 443))
    attempt("connect_ip", lambda: socket.create_connection(("93.184.215.14", 80), timeout=1))
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    attempt("udp_sendto", lambda: udp.sendto(b"x", ("8.8.8.8", 53)))
    attempt("urllib", lambda: urllib.request.urlopen("https://example.com", timeout=1))
    with netguard.allow_update_check():
        attempt("other_host_inside_context", lambda: socket.getaddrinfo("example.com", 443))
        attempt("urllib_other_url_inside_context",
                lambda: urllib.request.urlopen("https://mimufs.com/other", timeout=1))

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    attempt("loopback", lambda: socket.create_connection(server.getsockname(), timeout=1).close())
    attempt("socketpair", lambda: [s.close() for s in socket.socketpair()])
    out["stats"] = [netguard.stats().installed, netguard.stats().blocked]
    print(json.dumps(out))
    """
)


@pytest.fixture(scope="module")
def probe() -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(result.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "name",
    [
        "dns",
        "dns_update_host_outside_context",
        "connect_ip",
        "udp_sendto",
        "urllib",
        "other_host_inside_context",
        "urllib_other_url_inside_context",
    ],
)
def test_outbound_traffic_is_blocked(probe: dict[str, object], name: str) -> None:
    assert probe[name] == "blocked"


@pytest.mark.parametrize("name", ["loopback", "socketpair"])
def test_local_traffic_is_allowed(probe: dict[str, object], name: str) -> None:
    assert str(probe[name]).startswith("allowed")


def test_stats_count_blocked_attempts(probe: dict[str, object]) -> None:
    installed, blocked = probe["stats"]  # type: ignore[misc]
    assert installed is True
    assert blocked >= 7


# ------------------------------------------------------- decision function (no hook needed)


def test_update_host_allowed_only_inside_context() -> None:
    args = ("mimufs.com", 443, 0, 1, 0, 0)
    assert netguard.decide("socket.getaddrinfo", args, updater_active=True) is None
    assert netguard.decide("socket.getaddrinfo", args, updater_active=False) is not None
    wrong_port = ("mimufs.com", 80, 0, 1, 0, 0)
    assert netguard.decide("socket.getaddrinfo", wrong_port, updater_active=True) is not None


def test_connect_only_to_resolved_update_ips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netguard, "_resolved_update_ips", {"185.199.108.153"})
    good = (None, ("185.199.108.153", 443))
    assert netguard.decide("socket.connect", good, updater_active=True) is None
    assert netguard.decide("socket.connect", good, updater_active=False) is not None
    other = (None, ("1.1.1.1", 443))
    assert netguard.decide("socket.connect", other, updater_active=True) is not None


def test_urllib_only_the_version_url() -> None:
    ok = (netguard.UPDATE_URL, None, {}, "GET")
    assert netguard.decide("urllib.Request", ok, updater_active=True) is None
    assert netguard.decide("urllib.Request", ok, updater_active=False) is not None


def test_resolve_outside_context_refused() -> None:
    with pytest.raises(netguard.NetworkBlockedError):
        netguard.resolve_update_host()
