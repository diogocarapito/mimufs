"""Entry point: ``python -m mimufs`` (Briefcase runs the app this way).

The network guard is installed before anything else is imported (CLAUDE.md rule 1).
"""

from __future__ import annotations

from mimufs import netguard

netguard.install()

import argparse  # noqa: E402
import sys  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from pathlib import Path  # noqa: E402

from mimufs import __version__  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mimufs", description="mimufs")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument(
        "--selftest", action="store_true", help="check the installation (no user data) and exit"
    )
    parser.add_argument("--selftest-out", type=Path, help="also write the selftest report here")
    parser.add_argument("--debug", action="store_true", help="log to the console too")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    netguard.install()  # idempotent; covers callers that import main() directly
    args, qt_args = _parser().parse_known_args(sys.argv[1:] if argv is None else argv)

    if args.version:
        if sys.stdout is not None:
            print(__version__)
        return 0

    from mimufs.logging_setup import setup_logging
    from mimufs.settings import log_dir

    console = (args.selftest or args.debug) and sys.stderr is not None
    setup_logging(None if args.selftest else log_dir(), console=console)

    if args.selftest:
        from mimufs import selftest

        return selftest.run(args.selftest_out)

    from mimufs.gui.app import run

    return run([sys.argv[0], *qt_args])


if __name__ == "__main__":
    sys.exit(main())
