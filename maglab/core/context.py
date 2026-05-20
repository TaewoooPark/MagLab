"""Context engineering — MAGLAB.md loading, system prompt assembly, and compaction (§5.5).

- Loads ``MAGLAB.md`` (the immortal file) and injects it into the system prompt.
- On compaction, **parameter names, provenance IDs, and job IDs** are always preserved.
- The system prompt assembles role, invariant principles, and the current MAGLAB.md.

No dependencies on other maglab submodules (uses only maglab.config).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maglab.config import load_config

# ---------------------------------------------------------------------------
# MAGLAB.md loader
# ---------------------------------------------------------------------------

_DEFAULT_MAGLAB_MD_PATHS: list[Path] = [
    Path.cwd() / "MAGLAB.md",
    Path(__file__).parent.parent.parent / "MAGLAB.md",
]


def load_maglab_md(path: Path | None = None) -> str:
    """Load the MAGLAB.md immortal file.

    Search order:
    1. ``path`` if explicitly provided
    2. ``MAGLAB.md`` in the current working directory
    3. ``MAGLAB.md`` at the package root

    Returns a minimal fallback string when no file is found.
    """
    candidates = [path] if path else _DEFAULT_MAGLAB_MD_PATHS
    for p in candidates:
        if p and p.is_file():
            return p.read_text(encoding="utf-8")
    return (
        "# MAGLAB.md (default fallback)\n\n"
        "MagLab — magnetism and spintronics research lifecycle copilot.\n"
        "The LLM does not compute numbers. It delegates to deterministic tools.\n"
    )


# ---------------------------------------------------------------------------
# Preserve-key extraction (compaction safety)
# ---------------------------------------------------------------------------

_PROVENANCE_PATTERN = re.compile(r"\bprov:[A-Za-z0-9_-]+\b")
_JOB_PATTERN = re.compile(r"\bjob:[A-Za-z0-9_-]+\b")
_PARAM_PATTERN = re.compile(r"\bparam:[A-Za-z0-9_.]+\b")


def extract_preserve_keys(text: str) -> dict[str, list[str]]:
    """Extract keys that must be preserved during compaction.

    Returns
    -------
    dict with keys:
        ``provenance_ids`` — ``prov:...`` patterns
        ``job_ids``        — ``job:...`` patterns
        ``param_names``    — ``param:...`` patterns
    """
    return {
        "provenance_ids": _PROVENANCE_PATTERN.findall(text),
        "job_ids": _JOB_PATTERN.findall(text),
        "param_names": _PARAM_PATTERN.findall(text),
    }


# ---------------------------------------------------------------------------
# Working context
# ---------------------------------------------------------------------------


@dataclass
class WorkingContext:
    """Working context within a single orchestrator session.

    Used to verify that preserve keys survive compaction.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    """Conversation history (list of role/content dicts)."""
    provenance_ids: list[str] = field(default_factory=list)
    """Provenance IDs mentioned in the current context."""
    job_ids: list[str] = field(default_factory=list)
    """Job IDs mentioned in the current context."""
    param_names: list[str] = field(default_factory=list)
    """Parameter names mentioned in the current context."""
    token_count: int = 0
    """Current estimated token count."""

    def add_message(self, role: str, content: str) -> None:
        """Add a message and automatically extract preserve keys."""
        self.messages.append({"role": role, "content": content})
        keys = extract_preserve_keys(content)
        self.provenance_ids = list(dict.fromkeys(self.provenance_ids + keys["provenance_ids"]))
        self.job_ids = list(dict.fromkeys(self.job_ids + keys["job_ids"]))
        self.param_names = list(dict.fromkeys(self.param_names + keys["param_names"]))
        # Simple token estimate: 4 characters ≈ 1 token
        self.token_count += max(1, len(content) // 4)

    def compact(self, summary: str) -> WorkingContext:
        """Compact the context to a summary.

        Preserve keys (provenance, job, param) must appear in the summary text.
        Any keys missing from the summary are appended explicitly at the end.

        Parameters
        ----------
        summary:
            Compressed summary text (produced by LLM or deterministic logic).

        Returns
        -------
        New WorkingContext — messages reduced to a single [system_summary], preserve keys retained.
        """
        # Append missing-key preservation annotations
        suffix_lines: list[str] = []
        for pid in self.provenance_ids:
            if pid not in summary:
                suffix_lines.append(f"[preserved-provenance] {pid}")
        for jid in self.job_ids:
            if jid not in summary:
                suffix_lines.append(f"[preserved-job] {jid}")
        for pname in self.param_names:
            if pname not in summary:
                suffix_lines.append(f"[preserved-param] {pname}")

        full_summary = summary
        if suffix_lines:
            full_summary = (
                summary + "\n\n<!-- compaction preserved keys -->\n" + "\n".join(suffix_lines)
            )

        new_ctx = WorkingContext()
        new_ctx.messages = [{"role": "user", "content": f"[Conversation summary]\n{full_summary}"}]
        new_ctx.provenance_ids = list(self.provenance_ids)
        new_ctx.job_ids = list(self.job_ids)
        new_ctx.param_names = list(self.param_names)
        new_ctx.token_count = max(1, len(full_summary) // 4)
        return new_ctx


# ---------------------------------------------------------------------------
# System prompt assembly
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """You are the orchestrator of MagLab — a magnetism and spintronics research lifecycle copilot.

## Invariant Principles

1. **The LLM (you) does not compute numbers directly.** All numerical values are delegated to deterministic tools (physics, sim, analysis).
2. **The LLM does not fabricate citations.** Citations come exclusively from the verified literature pool.
3. **The LLM does not generate figure data.** Figures are authored via code/vectors.
4. Every output carries Provenance (DataPoint, citation, decision source, and lineage).
5. The human is the author and responsible party. The LLM handles reasoning, planning, tool selection, and draft text.

## Autonomy Mode

Current mode: {autonomy_mode}

## Project Context (MAGLAB.md)

{maglab_md}

## Active Workspace

{workspace_context}

## Available Deterministic Tools

{tool_context}

## Additional Guidelines

- Trust only the results returned by deterministic tool calls.
- Say "I don't know" when uncertain. Do not fabricate numerical estimates.
- Do not perform irreversible actions (file deletion, external writes) without human approval.
"""


def build_system_prompt(
    maglab_md_path: Path | None = None,
    extra_context: str = "",
) -> str:
    """Assemble the system prompt.

    Parameters
    ----------
    maglab_md_path:
        Path to MAGLAB.md (None → auto-search).
    extra_context:
        Additional context string (JIT-injected from skills or memory).
    """
    cfg = load_config()
    maglab_md = load_maglab_md(maglab_md_path)
    try:
        from maglab.workspace import workspace_summary

        workspace_context = workspace_summary()
    except Exception:
        workspace_context = "Current workspace root: unavailable"
    try:
        from maglab.llm.providers import prompt_for_config

        provider_context = prompt_for_config(cfg)
    except Exception:
        provider_context = ""
    try:
        from maglab.llm.tools import get_registered_tools

        tools = get_registered_tools()
        if tools:
            tool_context = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)
        else:
            tool_context = "No MagLab LLM tools are currently registered."
    except Exception:
        tool_context = "MagLab LLM tool list unavailable."
    prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        autonomy_mode=cfg.autonomy.mode,
        maglab_md=maglab_md,
        workspace_context=workspace_context,
        tool_context=tool_context,
    )
    if provider_context:
        prompt += f"\n## Runtime Provider Profile\n\n{provider_context}\n"
    if extra_context:
        prompt += f"\n## JIT Additional Context\n\n{extra_context}\n"
    return prompt


# ---------------------------------------------------------------------------
# ContextEngine
# ---------------------------------------------------------------------------


class ContextEngine:
    """Orchestrator context management engine.

    - Assembles and refreshes the system prompt
    - Maintains the working context
    - Detects compaction threshold and calls compact()
    """

    # Fraction of the context window at which compaction starts
    COMPACT_THRESHOLD = 0.85

    def __init__(
        self,
        context_window: int = 200_000,
        maglab_md_path: Path | None = None,
    ) -> None:
        self._context_window = context_window
        self._maglab_md_path = maglab_md_path
        self._system_prompt = build_system_prompt(maglab_md_path)
        self._working: WorkingContext = WorkingContext()
        # Pre-compute system prompt token estimate
        self._system_tokens = max(1, len(self._system_prompt) // 4)

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def working(self) -> WorkingContext:
        return self._working

    def add_turn(self, role: str, content: str) -> None:
        """Add a conversation turn."""
        self._working.add_message(role, content)

    def needs_compaction(self) -> bool:
        """Return True if compaction is needed."""
        used = self._system_tokens + self._working.token_count
        return used / self._context_window >= self.COMPACT_THRESHOLD

    def compact(self, summary: str) -> None:
        """Replace the current context with a summary. Preserve keys are retained."""
        self._working = self._working.compact(summary)

    def refresh_system_prompt(self, extra_context: str = "") -> None:
        """Re-read MAGLAB.md and refresh the system prompt."""
        self._system_prompt = build_system_prompt(self._maglab_md_path, extra_context)
        self._system_tokens = max(1, len(self._system_prompt) // 4)

    def get_messages_for_llm(self) -> list[dict[str, Any]]:
        """Return the message list to pass to the LLM API.

        The first element is always the system-role system prompt.
        """
        system_msg = {"role": "system", "content": self._system_prompt}
        return [system_msg] + self._working.messages
