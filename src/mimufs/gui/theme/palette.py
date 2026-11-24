"""Two themes, one set of token names (docs/ui/README.md), turned into a QPalette and QSS.

Widgets never hard-code colours: they set an ``objectName`` or a ``role``/``variant``/``state``
dynamic property, and the generated stylesheet styles them. Icons are recoloured from the same
tokens (:mod:`mimufs.gui.iconset`).
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

ThemeName = Literal["dark", "light"]
ThemeSetting = Literal["system", "dark", "light"]

TOKENS: dict[ThemeName, dict[str, str]] = {
    "dark": {
        "bg": "#0E1116",
        "chrome": "#0B0D11",
        "panel": "#141921",
        "panel2": "#10141A",
        "border": "#232A35",
        "line": "#1E252F",
        "text": "#D7DDE4",
        "strong": "#F1F4F8",
        "muted": "#8B95A3",
        "accent": "#FBBF24",
        "accent_text": "#FBBF24",
        "on_accent": "#0E1116",
        "ok": "#4ADE80",
        "warn": "#FBBF24",
        "err": "#F87171",
        "pend": "#8B95A3",
    },
    "light": {
        "bg": "#F4F5F7",
        "chrome": "#E9ECF0",
        "panel": "#FFFFFF",
        "panel2": "#F8F9FA",
        "border": "#D6DBE1",
        "line": "#E6E9ED",
        "text": "#1F2630",
        "strong": "#0E1116",
        "muted": "#59626F",
        "accent": "#B45309",
        "accent_text": "#9A4708",
        "on_accent": "#FFFFFF",
        "ok": "#15803D",
        "warn": "#B45309",
        "err": "#B91C1C",
        "pend": "#6B7280",
    },
}

#: Preferred families, bundled (Inter, JetBrains Mono; OFL) or the closest system font.
UI_FAMILIES = ("Inter", "Segoe UI", "SF Pro Text", ".AppleSystemUIFont", "Cantarell", "Noto Sans")
MONO_FAMILIES = (
    "JetBrains Mono", "SF Mono", "Menlo", "Cascadia Mono", "Consolas", "DejaVu Sans Mono",
    "Liberation Mono",
)  # fmt: skip


def system_theme() -> ThemeName:
    hints = QGuiApplication.styleHints()
    return "light" if hints.colorScheme() == Qt.ColorScheme.Light else "dark"


def effective_theme(setting: ThemeSetting) -> ThemeName:
    """The theme to paint: the user's choice, or the system's when set to ``system``."""
    return system_theme() if setting == "system" else setting


def _pick_family(preferred: tuple[str, ...], fallback: QFontDatabase.SystemFont) -> str:
    available = set(QFontDatabase.families())
    for family in preferred:
        if family in available:
            return family
    return QFontDatabase.systemFont(fallback).family()


def font_families() -> tuple[str, str]:
    """(UI family, monospace family) available on this machine."""
    return (
        _pick_family(UI_FAMILIES, QFontDatabase.SystemFont.GeneralFont),
        _pick_family(MONO_FAMILIES, QFontDatabase.SystemFont.FixedFont),
    )


def build_palette(theme: ThemeName) -> QPalette:
    t = TOKENS[theme]
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t["bg"],
        QPalette.ColorRole.WindowText: t["text"],
        QPalette.ColorRole.Base: t["panel"],
        QPalette.ColorRole.AlternateBase: t["panel2"],
        QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.BrightText: t["strong"],
        QPalette.ColorRole.Button: t["panel"],
        QPalette.ColorRole.ButtonText: t["strong"],
        QPalette.ColorRole.ToolTipBase: t["panel"],
        QPalette.ColorRole.ToolTipText: t["text"],
        QPalette.ColorRole.PlaceholderText: t["muted"],
        QPalette.ColorRole.Highlight: t["accent"],
        QPalette.ColorRole.HighlightedText: t["on_accent"],
        QPalette.ColorRole.Link: t["accent_text"],
        QPalette.ColorRole.Mid: t["border"],
        QPalette.ColorRole.Midlight: t["line"],
        QPalette.ColorRole.Dark: t["chrome"],
    }
    for role, colour in roles.items():
        p.setColor(role, QColor(colour))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["muted"]))
    return p


_QSS = """
QWidget {{ font-family: "{ui}"; font-size: 13px; color: {text}; }}
QMainWindow, QDialog {{ background: {bg}; }}
QToolTip {{ background: {panel}; color: {text}; border: 1px solid {border}; padding: 6px; }}

#TitleBar {{ background: {chrome}; border-bottom: 1px solid {border}; }}
#AppName {{ font-family: "{mono}"; font-size: 14px; font-weight: 700; color: {accent_text}; }}
#ProjectName {{ font-family: "{mono}"; font-size: 12px; color: {muted}; }}
#NetBadge {{ font-family: "{mono}"; font-size: 12px; }}
#NetBadge[state="ok"] {{ color: {ok}; }}
#NetBadge[state="warn"] {{ color: {warn}; }}

QLabel[role="kicker"], QLabel[role="section"] {{
    font-family: "{mono}"; font-size: 11px; font-weight: 600; color: {muted};
}}
QLabel[role="h1"] {{ font-size: 28px; font-weight: 700; color: {strong}; }}
QLabel[role="h2"] {{ font-size: 17px; font-weight: 700; color: {strong}; }}
QLabel[role="muted"] {{ color: {muted}; }}
QLabel[role="body"] {{ color: {text}; font-size: 14px; }}

#UnsupportedWarning {{ color: {err}; font-weight: 600; }}

#Card {{ background: {panel}; border: 1px solid {border}; border-radius: 6px; }}
#Card QLabel {{ background: transparent; }}

QPushButton {{
    background: {panel}; color: {strong}; border: 1px solid {border};
    border-radius: 4px; padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {muted}; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {muted}; background: {panel2}; }}
QPushButton[variant="primary"] {{
    background: {accent}; color: {on_accent}; border-color: {accent};
}}
QPushButton[variant="primary"]:disabled {{
    background: {panel2}; color: {muted}; border-color: {border};
}}

QToolButton#IconButton {{
    background: {panel2}; border: 1px solid {border}; border-radius: 4px; padding: 5px;
}}
QToolButton#IconButton:hover {{ border-color: {muted}; }}
QToolButton#IconButton:disabled {{ background: transparent; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""


def build_qss(theme: ThemeName, ui_family: str = "Inter", mono_family: str = "Menlo") -> str:
    return _QSS.format(ui=ui_family, mono=mono_family, **TOKENS[theme])


def apply_theme(app: QApplication, theme: ThemeName) -> None:
    """Fusion + palette + generated stylesheet for the whole application."""
    if app.style().name().casefold() != "fusion":
        app.setStyle("Fusion")
    ui, mono = font_families()
    font = QFont(ui)
    font.setPixelSize(13)
    app.setFont(font)
    app.setPalette(build_palette(theme))
    app.setStyleSheet(build_qss(theme, ui, mono))
    app.setProperty("mimufs_theme", theme)


def current_theme(app: QApplication) -> ThemeName:
    value = app.property("mimufs_theme")
    return "light" if value == "light" else "dark"
