"""mimufs: guided, local-only processing of MIM@UF reports."""

from importlib.metadata import PackageNotFoundError, version

try:
    # pyproject.toml is the single source; Briefcase installs the app's dist-info too.
    __version__ = version("mimufs")
except PackageNotFoundError:  # pragma: no cover - running from a bare source tree
    __version__ = "0.0.0+unknown"
