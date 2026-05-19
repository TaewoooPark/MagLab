"""Spin precession animation spinner.

Frame cycle modelled on Larmor precession:
``↑ ↗ → ↘ ↓ ↙ ← ↖``

Accessibility: the spinner is suppressed and replaced with static text in
``NO_COLOR`` · ``TERM=dumb`` · ``MAGLAB_NO_ANIMATION`` environments.

Design rationale: §7.4, §7.6 (plan/02-delivery.md).
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.progress import SpinnerColumn

# ---------------------------------------------------------------------------
# Larmor precession frames
# ---------------------------------------------------------------------------

PRECESSION_FRAMES: list[str] = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]

#: Static fallback symbol (used when animation is suppressed)
STATIC_SYMBOL = "⟳"

_FRAME_INTERVAL = 0.12  # seconds


# ---------------------------------------------------------------------------
# Accessibility / environment checks
# ---------------------------------------------------------------------------


def _no_animation() -> bool:
    """Return True when animation should be suppressed.

    Returns True when any of the following is set:
    - ``NO_COLOR``
    - ``TERM=dumb``
    - ``MAGLAB_NO_ANIMATION``
    - ``MAGLAB_SCREEN_READER``
    """
    return any(
        [
            "NO_COLOR" in os.environ,
            os.environ.get("TERM", "").lower() == "dumb",
            bool(os.environ.get("MAGLAB_NO_ANIMATION", "")),
            bool(os.environ.get("MAGLAB_SCREEN_READER", "")),
        ]
    )


# ---------------------------------------------------------------------------
# Spinner column (for rich Progress)
# ---------------------------------------------------------------------------


def precession_spinner_column() -> SpinnerColumn:
    """Return a rich SpinnerColumn using Larmor precession frames.

    :returns: Custom SpinnerColumn instance.
    """
    from rich.progress import SpinnerColumn
    from rich.spinner import Spinner

    spinner = Spinner("line", text="", speed=1 / _FRAME_INTERVAL)
    # Directly replace the frames on the rich Spinner
    spinner.frames = PRECESSION_FRAMES
    col = SpinnerColumn(spinner_name="line")
    col.spinner = spinner  # type: ignore[attr-defined]
    return col


# ---------------------------------------------------------------------------
# Context manager spinner (Live-based)
# ---------------------------------------------------------------------------


class _PrecessionSpinner:
    """Larmor precession spinner context manager.

    Prints a single static symbol and exits immediately in non-TTY /
    suppressed environments.
    """

    def __init__(self, text: str = "", color: str = "#38bdf8") -> None:
        """Initialise.

        :param text: Text to display beside the spinner.
        :param color: Spinner glyph colour (hex).
        """
        self._text = text
        self._color = color
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        """Cycle through frames in a background thread."""
        from rich.console import Console

        console = Console()
        idx = 0
        while not self._stop_event.is_set():
            frame = PRECESSION_FRAMES[idx % len(PRECESSION_FRAMES)]
            label = f" {self._text}" if self._text else ""
            console.print(
                f"[{self._color}]{frame}[/]{label}",
                end="\r",
                highlight=False,
            )
            idx += 1
            time.sleep(_FRAME_INTERVAL)

    def start(self) -> None:
        """Start the spinner."""
        if _no_animation():
            from rich.console import Console

            Console().print(f"{STATIC_SYMBOL} {self._text}" if self._text else STATIC_SYMBOL)
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the spinner."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)

    def __enter__(self) -> _PrecessionSpinner:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()


@contextmanager
def spin(text: str = "", color: str = "#38bdf8") -> Generator[None, None, None]:
    """Larmor precession spinner context manager.

    Prints a single static text string in accessibility-suppressed environments.

    :param text: Text to display beside the spinner.
    :param color: Spinner colour (hex).

    Example usage::

        with spin("Computing"):
            heavy_computation()
    """
    spinner = _PrecessionSpinner(text=text, color=color)
    with spinner:
        yield
