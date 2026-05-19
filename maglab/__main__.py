"""maglab CLI entry point — console script `maglab` and `python -m maglab`."""

from __future__ import annotations

from maglab.cli import app


def main() -> None:
    """Console script entry point."""
    app()


if __name__ == "__main__":
    main()
