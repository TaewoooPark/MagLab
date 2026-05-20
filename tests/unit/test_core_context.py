"""maglab.core.context unit tests — deterministic, no network/LLM."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from maglab.core.context import (
    ContextEngine,
    WorkingContext,
    build_system_prompt,
    extract_preserve_keys,
    load_maglab_md,
)

# ---------------------------------------------------------------------------
# load_maglab_md
# ---------------------------------------------------------------------------


def test_load_maglab_md_from_path(tmp_path: Path) -> None:
    p = tmp_path / "MAGLAB.md"
    p.write_text("# Test\nProject context.", encoding="utf-8")
    content = load_maglab_md(p)
    assert "Project context" in content


def test_load_maglab_md_fallback_when_missing(tmp_path: Path) -> None:
    content = load_maglab_md(tmp_path / "nonexistent.md")
    assert "MagLab" in content
    # fallback must not be empty
    assert len(content) > 10


# ---------------------------------------------------------------------------
# extract_preserve_keys
# ---------------------------------------------------------------------------


def test_extract_provenance_ids() -> None:
    text = "Result prov:abc123 reference. Also prov:xyz789."
    keys = extract_preserve_keys(text)
    assert "prov:abc123" in keys["provenance_ids"]
    assert "prov:xyz789" in keys["provenance_ids"]


def test_extract_job_ids() -> None:
    text = "Job job:run-001 done. job:sim-042 failed."
    keys = extract_preserve_keys(text)
    assert "job:run-001" in keys["job_ids"]
    assert "job:sim-042" in keys["job_ids"]


def test_extract_param_names() -> None:
    text = "Parameters param:alpha_DW and param:Ms_CoFeB used."
    keys = extract_preserve_keys(text)
    assert "param:alpha_DW" in keys["param_names"]
    assert "param:Ms_CoFeB" in keys["param_names"]


def test_extract_empty_text() -> None:
    keys = extract_preserve_keys("")
    assert keys["provenance_ids"] == []
    assert keys["job_ids"] == []
    assert keys["param_names"] == []


# ---------------------------------------------------------------------------
# WorkingContext
# ---------------------------------------------------------------------------


def test_add_message_accumulates() -> None:
    ctx = WorkingContext()
    ctx.add_message("user", "prov:abc reference.")
    ctx.add_message("assistant", "job:run-1 done.")
    assert len(ctx.messages) == 2
    assert "prov:abc" in ctx.provenance_ids
    assert "job:run-1" in ctx.job_ids


def test_add_message_deduplicates_keys() -> None:
    ctx = WorkingContext()
    ctx.add_message("user", "prov:abc reference.")
    ctx.add_message("assistant", "prov:abc again.")
    assert ctx.provenance_ids.count("prov:abc") == 1


def test_token_count_increases() -> None:
    ctx = WorkingContext()
    before = ctx.token_count
    ctx.add_message("user", "A" * 100)
    assert ctx.token_count > before


# ---------------------------------------------------------------------------
# WorkingContext.compact
# ---------------------------------------------------------------------------


def test_compact_preserves_provenance_in_summary() -> None:
    ctx = WorkingContext()
    ctx.add_message("user", "prov:abc123 reference.")
    summary = "Summary: prov:abc123 included."
    new_ctx = ctx.compact(summary)
    # preserved key must exist in new context
    assert "prov:abc123" in new_ctx.provenance_ids


def test_compact_appends_missing_keys_to_summary() -> None:
    ctx = WorkingContext()
    ctx.add_message("user", "prov:hidden123 reference.")
    # if "prov:hidden123" is not in summary, it must be appended as a suffix
    new_ctx = ctx.compact("Summary with no keys.")
    assert "prov:hidden123" in new_ctx.provenance_ids
    content = new_ctx.messages[0]["content"]
    assert "prov:hidden123" in content


def test_compact_reduces_to_single_message() -> None:
    ctx = WorkingContext()
    for i in range(5):
        ctx.add_message("user", f"Message {i}")
    new_ctx = ctx.compact("Summary")
    assert len(new_ctx.messages) == 1
    # The compacted summary must be a user-role message (NOT system) so that
    # get_messages_for_llm() does not produce two system-role entries, which
    # would violate the Anthropic Messages API contract.
    assert new_ctx.messages[0]["role"] == "user"
    assert "[Conversation summary]" in new_ctx.messages[0]["content"]


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_contains_principles(tmp_path: Path) -> None:
    p = tmp_path / "MAGLAB.md"
    p.write_text("# MAGLAB\nTest context.", encoding="utf-8")
    prompt = build_system_prompt(maglab_md_path=p)
    assert "LLM" in prompt
    assert "Test context" in prompt


def test_build_system_prompt_includes_autonomy_mode(tmp_path: Path) -> None:
    p = tmp_path / "MAGLAB.md"
    p.write_text("# M", encoding="utf-8")
    prompt = build_system_prompt(maglab_md_path=p)
    # autonomy mode value must be present
    assert "copilot" in prompt or "semi-auto" in prompt or "autonomous" in prompt


def test_build_system_prompt_with_extra_context(tmp_path: Path) -> None:
    p = tmp_path / "MAGLAB.md"
    p.write_text("# M", encoding="utf-8")
    prompt = build_system_prompt(maglab_md_path=p, extra_context="JIT injected content XYZ")
    assert "JIT injected content XYZ" in prompt


def test_build_system_prompt_includes_active_workspace_context(tmp_path: Path) -> None:
    p = tmp_path / "MAGLAB.md"
    p.write_text("# M", encoding="utf-8")
    with patch("maglab.workspace.workspace_summary", return_value="workspace-root-test"):
        prompt = build_system_prompt(maglab_md_path=p)
    assert "## Active Workspace" in prompt
    assert "workspace-root-test" in prompt


# ---------------------------------------------------------------------------
# ContextEngine
# ---------------------------------------------------------------------------


def test_context_engine_system_prompt_not_empty(tmp_path: Path) -> None:
    p = tmp_path / "MAGLAB.md"
    p.write_text("# M\nContent.", encoding="utf-8")
    engine = ContextEngine(maglab_md_path=p)
    assert len(engine.system_prompt) > 50


def test_context_engine_add_turn() -> None:
    engine = ContextEngine()
    engine.add_turn("user", "Hello.")
    engine.add_turn("assistant", "Hello.")
    assert len(engine.working.messages) == 2


def test_context_engine_get_messages_for_llm() -> None:
    engine = ContextEngine()
    engine.add_turn("user", "Question")
    msgs = engine.get_messages_for_llm()
    # first element must be system role
    assert msgs[0]["role"] == "system"
    assert len(msgs) == 2


def test_context_engine_needs_compaction_false_when_small() -> None:
    engine = ContextEngine(context_window=200_000)
    engine.add_turn("user", "Short message.")
    assert not engine.needs_compaction()


def test_context_engine_needs_compaction_true_when_large() -> None:
    engine = ContextEngine(context_window=100)  # very small window
    engine.add_turn("user", "A" * 500)
    assert engine.needs_compaction()


def test_context_engine_compact_preserves_working_keys() -> None:
    engine = ContextEngine()
    engine.add_turn("user", "prov:test-id reference.")
    engine.compact("Summary.")
    assert "prov:test-id" in engine.working.provenance_ids


# ---------------------------------------------------------------------------
# Regression: F1 (R7) — no double system-role after compaction
# ---------------------------------------------------------------------------


def test_get_messages_for_llm_has_exactly_one_system_role_after_compaction() -> None:
    """After compaction, get_messages_for_llm() must yield exactly one system-role
    entry (the primary system prompt).  The Anthropic Messages API forbids a
    second ``role="system"`` inside the messages array; prior to R7-F1 the
    compacted summary was stored with role="system", producing a 400 Bad Request
    on the first LLM call following compaction.
    """
    engine = ContextEngine()
    engine.add_turn("user", "Measure prov:abc at 300 K.")
    engine.add_turn("assistant", "Done. job:run-001 completed.")
    engine.compact("Session so far: measured prov:abc, job:run-001 finished.")

    msgs = engine.get_messages_for_llm()

    system_entries = [m for m in msgs if m["role"] == "system"]
    assert len(system_entries) == 1, (
        f"Expected exactly 1 system-role message after compaction, got {len(system_entries)}: "
        f"{system_entries}"
    )

    # The compacted summary must still be present as a non-system message
    non_system = [m for m in msgs if m["role"] != "system"]
    assert any("[Conversation summary]" in m["content"] for m in non_system), (
        "Compacted summary not found as a non-system message in get_messages_for_llm() output"
    )
