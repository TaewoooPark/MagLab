"""Machine-readable JSON emission for ``--json`` command output.

``rich.Console`` is the right tool for everything a human reads, but it is the
wrong one for a payload another program parses. ``Console.print_json`` applies
syntax highlighting, and ``Console.print`` runs plain strings through Rich's
highlighter and word-wraps them at the terminal width. Either turns a documented
``--json`` contract into something ``json.load`` rejects:

- Colour is emitted whenever Rich decides to colourise. ``FORCE_COLOR`` — set by
  default on many CI runners — makes that happen even when the output is a pipe,
  so ``maglab config show > config.json`` yields ANSI escapes, not JSON.
- Word wrapping can split a long string value across lines.

JSON therefore goes to stdout untouched.
"""

from __future__ import annotations

import json
import sys
from typing import Any

__all__ = ["emit_json", "emit_json_text"]


def emit_json_text(text: str) -> None:
    """Write pre-serialised JSON *text* to stdout verbatim."""
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    sys.stdout.flush()


def emit_json(payload: Any, *, indent: int = 2) -> None:
    """Serialise *payload* and write it to stdout as unformatted JSON."""
    emit_json_text(json.dumps(payload, ensure_ascii=False, indent=indent))
