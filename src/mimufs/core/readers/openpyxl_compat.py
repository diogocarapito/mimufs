"""openpyxl compatibility patch for MIM@UF exports (TECH_SPECS §5.0.1).

Diogo's working code patches the **private** module ``openpyxl.worksheet._reader`` (the
``WorkSheetParser`` used by read-only workbooks) so that openpyxl can read MIM@UF exports.
Because the module is private:

* the patch lives here, alone, behind an idempotent :func:`apply`;
* openpyxl is pinned to :data:`PATCHED_FOR` in ``pyproject.toml``, and :func:`apply` refuses
  to run on another version, so an upgrade fails in CI instead of silently misreading files;
* it is applied once, when :mod:`mimufs.core.readers.excel` is imported, never globally at
  app start-up.

TODO(Diogo): the patch itself is still to be ported. Until then :func:`apply` only checks the
version, and ``tests/core/test_openpyxl_compat.py::test_mimuf_quirk_needs_patch`` is xfail.
Document here which MIM@UF quirk it works around when it lands.
"""

from __future__ import annotations

import openpyxl

PATCHED_FOR = "3.1.5"

_applied = False


class OpenpyxlVersionError(RuntimeError):
    """openpyxl is not the version the compat patch was written for."""


def apply() -> None:
    """Install the patch (idempotent)."""
    global _applied
    if _applied:
        return
    if openpyxl.__version__ != PATCHED_FOR:
        raise OpenpyxlVersionError(
            f"openpyxl {openpyxl.__version__} is installed but the MIM@UF compatibility patch "
            f"was written for {PATCHED_FOR}; re-check readers/openpyxl_compat.py before "
            "changing the pin."
        )
    # The patch of openpyxl.worksheet._reader goes here (pending input from Diogo).
    _applied = True


def is_applied() -> bool:
    return _applied
