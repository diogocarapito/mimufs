"""Locate the Java runtime that tabula-java runs on (TECH_SPECS §10.1, §16.2).

Release bundles ship a jlinked JRE in ``mimufs/_runtime/jre`` (built by
``packaging/jre/build_jre.sh``), so users never need Java installed: SPMS PCs can't install it.
:func:`configure` puts that runtime first on ``PATH`` and sets ``JAVA_HOME``, so tabula never
uses (or needs) a Java installed on the machine.

From source (development), it falls back to ``JAVA_HOME``, then to a Java on ``PATH``, then
to the Homebrew ``openjdk@21`` keg. Each candidate is verified by running ``java -version``,
because macOS ships a ``/usr/bin/java`` stub that only prints "Unable to locate a Java Runtime".
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path

log = logging.getLogger(__name__)

JAVA_EXE = "java.exe" if sys.platform == "win32" else "java"
_DEV_CANDIDATES = (
    Path("/opt/homebrew/opt/openjdk@21"),
    Path("/usr/local/opt/openjdk@21"),
    Path("/opt/homebrew/opt/openjdk"),
    Path("/usr/local/opt/openjdk"),
)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console flash


class JavaUnavailableError(RuntimeError):
    """No usable Java runtime (missing, or blocked e.g. by antivirus)."""


@dataclass(frozen=True)
class JavaRuntime:
    home: Path
    executable: Path
    bundled: bool
    version: str  # first line of ``java -version``


def bundled_home() -> Path | None:
    """The jlinked JRE shipped inside the app, if present."""
    with as_file(files("mimufs")) as package_dir:
        home = Path(package_dir) / "_runtime" / "jre"
    return home if (home / "bin" / JAVA_EXE).is_file() else None


def _probe(home: Path, *, bundled: bool) -> JavaRuntime | None:
    exe = home / "bin" / JAVA_EXE
    if not exe.is_file():
        return None
    try:
        result = subprocess.run(
            [str(exe), "-version"],
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        log.warning("java at %s failed to start", "bundled JRE" if bundled else home)
        return None
    if result.returncode != 0:
        return None
    first = (result.stderr or result.stdout).strip().splitlines()
    return JavaRuntime(home, exe, bundled, first[0] if first else "")


def _dev_candidates() -> list[Path]:
    candidates: list[Path] = []
    if os.environ.get("JAVA_HOME"):
        candidates.append(Path(os.environ["JAVA_HOME"]))
    on_path = shutil.which("java")
    if on_path:
        candidates.append(Path(on_path).resolve().parent.parent)
    candidates.extend(_DEV_CANDIDATES)
    # The Homebrew keg layout: libexec/openjdk.jdk/Contents/Home holds a full JDK.
    candidates.extend(c / "libexec" / "openjdk.jdk" / "Contents" / "Home" for c in _DEV_CANDIDATES)
    return candidates


def find_java() -> JavaRuntime | None:
    """The bundled JRE if present; otherwise (development only) a system Java."""
    home = bundled_home()
    if home is not None:
        return _probe(home, bundled=True)
    for candidate in _dev_candidates():
        runtime = _probe(candidate, bundled=False)
        if runtime is not None:
            log.info("no bundled JRE: using a system Java (development)")
            return runtime
    return None


_configured: JavaRuntime | None = None


def configure() -> JavaRuntime:
    """Make ``java`` on PATH resolve to the runtime mimufs uses. Idempotent."""
    global _configured
    if _configured is not None:
        return _configured
    runtime = find_java()
    if runtime is None:
        raise JavaUnavailableError("no usable Java runtime found")
    bin_dir = str(runtime.executable.parent)
    path = os.environ.get("PATH", "")
    if path.split(os.pathsep)[:1] != [bin_dir]:
        os.environ["PATH"] = bin_dir + (os.pathsep + path if path else "")
    os.environ["JAVA_HOME"] = str(runtime.home)
    _configured = runtime
    return runtime


def reset() -> None:
    """Forget the configured runtime (tests)."""
    global _configured
    _configured = None
