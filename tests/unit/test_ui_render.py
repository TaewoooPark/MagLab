"""UI render tests for trace and banner helpers."""

from __future__ import annotations

import io

from rich.console import Console

from maglab.ui.banner import _render_pixel_wordmark
from maglab.ui.render import ReplTraceRenderer
from maglab.ui.spinner import STATIC_SYMBOL
from maglab.ui.theme import Theme


def test_repl_trace_renderer_prints_activity_guidance_without_tty() -> None:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=120)
    renderer = ReplTraceRenderer(console=console)

    renderer.emit({"kind": "llm_start", "stage": "default", "model": "gpt-test", "tool_count": 35})
    renderer.emit(
        {
            "kind": "llm_done",
            "elapsed_sec": 1.25,
            "tool_calls": 0,
            "prompt_tokens": 10,
            "completion_tokens": 5,
        }
    )

    output = buffer.getvalue()
    assert "LLM working" in output
    assert "started" in output
    assert "stop Ctrl+C" in output
    assert "answer frame received" in output
    assert "1.25s" in output


def test_repl_trace_renderer_honors_no_animation(
    monkeypatch,
) -> None:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=True, width=120)
    monkeypatch.setenv("MAGLAB_NO_ANIMATION", "1")
    renderer = ReplTraceRenderer(console=console)

    renderer.emit({"kind": "llm_start", "stage": "default", "model": "gpt-test"})
    renderer.close()

    output = buffer.getvalue()
    assert STATIC_SYMBOL in output
    assert "elapsed" not in output
    assert "stop Ctrl+C" in output


def test_theme_pixel_wordmark_uses_theme_texture() -> None:
    wordmark = _render_pixel_wordmark(Theme.load("moke"))

    assert "▨" in wordmark
    assert "▧" in wordmark
    assert "MAGLAB" not in wordmark
