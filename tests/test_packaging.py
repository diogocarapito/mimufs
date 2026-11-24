"""Briefcase configuration (TECH_SPECS §16): icons, locked versions and bundle trimming."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

import mimufs

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
APP = PYPROJECT["tool"]["briefcase"]["app"]["mimufs"]
CLEANUP: list[str] = APP["cleanup_paths"]

# A miniature bundle with the real file names of each OS (macOS / Linux / Windows).
REMOVED = [
    "app_packages/PySide6/QtNetwork.abi3.so",
    "app_packages/PySide6/QtNetwork.pyd",
    "app_packages/PySide6/Qt6Network.dll",
    "app_packages/PySide6/Qt/lib/QtNetwork.framework/QtNetwork",
    "app_packages/PySide6/Qt/lib/libQt6Network.so.6",
    "app_packages/PySide6/Qt/lib/QtQml.framework/QtQml",
    "app_packages/PySide6/Qt/lib/libQt6QuickControls2.so.6",
    "app_packages/PySide6/Qt6Qml.dll",
    "app_packages/PySide6/libpyside6qml.abi3.6.12.dylib",
    "app_packages/PySide6/Qt/plugins/tls/libqopensslbackend.dylib",
    "app_packages/PySide6/plugins/tls/qschannelbackend.dll",
    "app_packages/PySide6/Qt/plugins/networkinformation/libqnetworkmanager.so",
    "app_packages/PySide6/Qt/plugins/generic/libqtuiotouchplugin.so",
    "app_packages/PySide6/Qt/plugins/platforms/libqvnc.so",
    "app_packages/PySide6/Qt/qml/QtQuick/qmldir",
    "app_packages/PySide6/Designer.app/Contents/Info.plist",
    "app_packages/PySide6/designer.exe",
    "app_packages/PySide6/QtWidgets.pyi",
    "app_packages/pyarrow/libarrow_s3.2600.dylib",
    "app_packages/pyarrow/_s3fs.cpython-312-darwin.so",
    "app_packages/pyarrow/_gcsfs.cpython-312-x86_64-linux-gnu.so",
    "app_packages/pyarrow/include/arrow/api.h",
    "app_packages/bin/pyside6-designer",
    "Frameworks/Python.framework/Versions/3.12/lib/python3.12/test/test_os.py",
    "Frameworks/Python.framework/Versions/3.12/lib/python3.12/tkinter/__init__.py",
]
KEPT = [
    "app_packages/PySide6/__init__.py",
    "app_packages/PySide6/QtCore.abi3.so",
    "app_packages/PySide6/QtGui.pyd",
    "app_packages/PySide6/QtWidgets.abi3.so",
    "app_packages/PySide6/QtSvg.abi3.so",
    "app_packages/PySide6/Qt6Core.dll",
    "app_packages/PySide6/Qt6Widgets.dll",
    "app_packages/PySide6/Qt6Svg.dll",
    "app_packages/PySide6/Qt/lib/QtGui.framework/QtGui",
    "app_packages/PySide6/Qt/lib/QtDBus.framework/QtDBus",
    "app_packages/PySide6/Qt/lib/libQt6XcbQpa.so.6",
    "app_packages/PySide6/Qt/lib/libQt6WaylandClient.so.6",
    "app_packages/PySide6/Qt/lib/libQt6OpenGL.so.6",
    "app_packages/PySide6/libpyside6.abi3.6.12.dylib",
    "app_packages/PySide6/support/__init__.py",
    "app_packages/PySide6/Qt/plugins/platforms/libqcocoa.dylib",
    "app_packages/PySide6/Qt/plugins/platforms/libqxcb.so",
    "app_packages/PySide6/Qt/plugins/platforms/libqoffscreen.so",
    "app_packages/PySide6/plugins/platforms/qwindows.dll",
    "app_packages/PySide6/Qt/plugins/imageformats/libqsvg.dylib",
    "app_packages/PySide6/Qt/plugins/iconengines/libqsvgicon.dylib",
    "app_packages/PySide6/Qt/plugins/styles/libqmacstyle.dylib",
    "app_packages/PySide6/Qt/translations/qtbase_pt.qm",
    "app_packages/pyarrow/libarrow.2600.dylib",
    "app_packages/pyarrow/libparquet.2600.dylib",
    "app_packages/pyarrow/lib.cpython-312-darwin.so",
    "app_packages/pyarrow/_fs.cpython-312-darwin.so",
    "app_packages/pydantic/networks.py",
    "app/mimufs/core/specs/reports/P01.01.L01.yaml",
    "app/mimufs/gui/icons/shield-check.svg",
    "app/mimufs/_runtime/jre/bin/java",
    "app/mimufs/_runtime/jre/lib/modules",
    "Frameworks/Python.framework/Versions/3.12/lib/python3.12/os.py",
    "Frameworks/Python.framework/Versions/3.12/lib/python3.12/unittest/__init__.py",
    "Frameworks/Python.framework/Versions/3.12/lib/python3.12/lib-dynload/_ssl.so",
]


def _apply_cleanup(bundle: Path) -> None:
    """What Briefcase does with ``cleanup_paths`` (commands/create.py)."""
    for pattern in CLEANUP:
        for path in bundle.glob(pattern):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()


def test_cleanup_removes_network_and_unused_parts_only(tmp_path: Path) -> None:
    for rel in [*REMOVED, *KEPT]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    _apply_cleanup(tmp_path)
    assert [rel for rel in REMOVED if (tmp_path / rel).exists()] == []
    assert [rel for rel in KEPT if not (tmp_path / rel).exists()] == []


def test_cleanup_patterns_are_safe_for_briefcase() -> None:
    for pattern in CLEANUP:
        assert pattern.startswith("**/"), pattern  # relative to whichever bundle layout
        assert "{" not in pattern, pattern  # Briefcase calls str.format(app=…) on each


def test_icons_exist_for_every_platform() -> None:
    base = ROOT / APP["icon"]
    assert base.with_suffix(".icns").read_bytes()[:4] == b"icns"
    assert base.with_suffix(".ico").read_bytes()[:4] == b"\x00\x00\x01\x00"
    for size in (16, 32, 64, 128, 256, 512):
        assert Path(f"{base}-{size}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (ROOT / "src" / "mimufs" / "gui" / "icons" / "app.png").is_file()


def test_version_has_one_source() -> None:
    assert "version" not in PYPROJECT["tool"]["briefcase"]
    assert "requires" not in APP  # Briefcase reads [project].dependencies itself
    assert mimufs.__version__ == PYPROJECT["project"]["version"]


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not on PATH")
def test_constraints_match_the_lock_file() -> None:
    """``packaging/constraints.txt`` pins bundles to uv.lock; regenerate it when the lock moves:

    uv export --no-dev --no-hashes --no-emit-project --no-header --format requirements-txt \\
        -o packaging/constraints.txt
    """
    exported = subprocess.run(
        ["uv", "export", "--no-dev", "--no-hashes", "--no-emit-project", "--no-header",
         "--format", "requirements-txt", "--frozen"],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=120,
    ).stdout  # fmt: skip
    committed = (ROOT / "packaging" / "constraints.txt").read_text(encoding="utf-8")
    assert committed.splitlines() == exported.splitlines()
    assert APP["requirement_installer_args"] == ["--constraint", "./packaging/constraints.txt"]


def test_bundle_scanner_flags_network_parts(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import check_bundle

    for rel in [*REMOVED[:6], *KEPT]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    assert len(check_bundle.offending(tmp_path)) >= 6
    _apply_cleanup(tmp_path)
    assert check_bundle.offending(tmp_path) == []
