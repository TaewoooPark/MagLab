"""Progress indicators, kept off stdout.

``Console.status`` renders a live spinner: it hides the cursor, repaints a frame,
then moves the cursor back and erases the line. Those are control sequences, and
on stdout they land in whatever the user is piping into — ahead of the payload.
``maglab explain --json | jq`` failed at column 1 for exactly that reason
whenever Rich decided to render live output (a terminal, or ``FORCE_COLOR``,
which many CI runners set by default).

stdout carries results; progress belongs on stderr, where curl, pip and docker
put theirs. A user watching a terminal still sees the spinner, and a pipe still
receives only data.
"""

from __future__ import annotations

from rich.console import Console

__all__ = ["status_console"]

status_console: Console = Console(stderr=True)
"""Console for spinners and progress — never the destination for results."""
