"""CLI command modules — Typer sub-apps grouped by implementation phase.

Each module exposes ``register(app)`` which attaches its commands to the
root ``maglab`` Typer application (see ``maglab/cli.py``).  Heavy or
optional dependencies must be imported lazily inside command callbacks so
that ``maglab --help`` works without the optional extras installed.
"""
