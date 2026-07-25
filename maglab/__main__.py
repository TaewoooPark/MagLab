"""maglab CLI entry point — console script `maglab` and `python -m maglab`."""

from __future__ import annotations

import sys

from maglab.cli import app
from maglab.config import ConfigError


def main() -> None:
    """Console script entry point."""
    try:
        app()
    except ConfigError as exc:
        # A broken config file would otherwise dump a tomllib/pydantic traceback
        # on *every* command, including the ones that repair it.
        print(f"maglab: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
