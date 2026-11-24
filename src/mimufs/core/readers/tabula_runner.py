"""Run tabula-java (via tabula-py) safely inside mimufs.

* Always the subprocess backend (``force_subprocess=True``; JPype is not installed): one Java
  start per PDF, and Java stays out of the app's process.
* Always the runtime chosen by :func:`java_runtime.configure` (the bundled JRE in releases).
* On Windows, the Java console window is suppressed: tabula-py calls ``subprocess.run`` without
  ``creationflags``, which flashes a console from a GUI app. tabula's backend gets a private
  shim of the ``subprocess`` module that adds ``CREATE_NO_WINDOW``; nothing else is patched.
* tabula-py logs tabula-java's stderr, which could echo PDF text, so its logger is silenced.
"""

from __future__ import annotations

import logging
import subprocess
import types
from pathlib import Path
from typing import Any

from mimufs.core.readers import java_runtime

JAVA_OPTIONS = [
    "-Djava.awt.headless=true",
    "-Dfile.encoding=UTF8",
    # Since Java 18, System.out uses stdout.encoding (the console code page, cp1252 on
    # Windows), not file.encoding; tabula-py decodes the CSV it prints as UTF-8.
    "-Dstdout.encoding=UTF-8",
    "-Dstderr.encoding=UTF-8",
    "-Xmx1g",
]


class TabulaError(RuntimeError):
    """tabula-java failed on this PDF. ``detail`` is safe to log."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _no_window_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    kwargs.setdefault("creationflags", java_runtime.NO_WINDOW)
    kwargs.setdefault("timeout", 600)
    return subprocess.run(*args, **kwargs)


_shim = types.ModuleType("subprocess_no_window")
_shim.__dict__.update(
    {name: getattr(subprocess, name) for name in dir(subprocess) if not name.startswith("__")}
)
_shim.run = _no_window_run  # type: ignore[attr-defined]


def _prepare() -> None:
    java_runtime.configure()
    import tabula.backend

    setattr(tabula.backend, "subprocess", _shim)  # noqa: B010  (only tabula's backend)
    logging.getLogger("tabula").setLevel(logging.CRITICAL)


def read_pdf_tables(path: Path, **options: Any) -> list[Any]:
    """``tabula.read_pdf`` with mimufs' safety settings; returns pandas DataFrames.

    ``options`` are tabula-py's (``pages``, ``lattice``, ``stream``, ``area``, ``columns``,
    ``pandas_options``…), so Diogo's working call can be ported unchanged.
    """
    _prepare()
    from tabula.errors import JavaNotFoundError
    from tabula.io import read_pdf

    options.setdefault("pages", "all")
    try:
        result = read_pdf(
            str(path),
            force_subprocess=True,
            silent=True,
            java_options=list(JAVA_OPTIONS),
            **options,
        )
    except JavaNotFoundError:
        raise java_runtime.JavaUnavailableError("java could not be started") from None
    except subprocess.CalledProcessError as exc:
        raise TabulaError(f"tabula-java exited with code {exc.returncode}") from None
    except subprocess.TimeoutExpired:
        raise TabulaError("tabula-java timed out") from None
    except Exception as exc:  # pandas parse errors etc.; the message may quote PDF text
        raise TabulaError(type(exc).__name__) from None
    return list(result) if isinstance(result, list) else [result]
