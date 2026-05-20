"""Subagent pool — agents/<name>.md load, isolated execution, and result verification (§5.16).

Subagent definition file conventions:
  - YAML frontmatter (name, description, tools, model, max_turns, context, etc.)
  - Body = system prompt

Six-element contract (§5.16):
  ① Single goal  ② Input spec  ③ Output schema  ④ Tool budget  ⑤ Source guide
  ⑥ Task boundary and ambiguity handling

Nested spawn depth limit: 2 levels.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from maglab.core.verify import Verifier

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Search paths
# ---------------------------------------------------------------------------

_PKG_ROOT = Path(__file__).parent.parent.parent
_BUNDLE_AGENTS_DIR = _PKG_ROOT / "agents"

_DEFAULT_AGENT_DIRS: list[Path] = [
    Path.cwd() / ".maglab" / "agents",
    _BUNDLE_AGENTS_DIR,
]

# ---------------------------------------------------------------------------
# Subagent definition data structures
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


class SubagentLoadError(Exception):
    """Error loading or parsing a subagent definition."""


class SubagentDef(BaseModel):
    """Subagent definition parsed from agents/<name>.md.

    Holds all frontmatter fields (§5.16).
    """

    name: str
    """Subagent identifier (kebab-case)."""
    description: str = ""
    """Trigger sentence the orchestrator uses to decide delegation."""
    tools: list[str] = Field(default_factory=list)
    """Least-privilege allowlist of permitted tools."""
    model: str = "haiku"
    """Model tier to use (opus/sonnet/haiku/inherit)."""
    max_turns: int = 10
    """Internal loop iteration limit."""
    effort: str = ""
    """Reasoning effort hint."""
    context: str = "isolated"
    """Default 'isolated'; 'fork' inherits parent context."""
    skills: list[str] = Field(default_factory=list)
    """List of skills to preload."""
    mcp_servers: list[str] = Field(default_factory=list)
    """MCP servers scoped to this agent."""
    hooks: list[str] = Field(default_factory=list)
    """Hooks to apply."""
    system_prompt: str = ""
    """Body of SKILL.md (= system prompt)."""
    source_file: str = ""
    """Path of the loaded file (for debugging)."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Subagent definition loader
# ---------------------------------------------------------------------------


def _parse_agent_md(path: Path) -> SubagentDef:
    """Parse an agents/<name>.md file and return a SubagentDef."""
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SubagentLoadError(f"[{path.name}] Missing YAML frontmatter (--- separator).")
    try:
        fm: dict[str, Any] = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SubagentLoadError(f"[{path.name}] YAML parse error: {exc}") from exc
    if not isinstance(fm, dict):
        raise SubagentLoadError(f"[{path.name}] frontmatter is not a dict.")
    if "name" not in fm:
        raise SubagentLoadError(f"[{path.name}] Missing 'name' field.")

    body = text[m.end() :].lstrip("\n")
    return SubagentDef(
        **{k: v for k, v in fm.items() if k in SubagentDef.model_fields},
        system_prompt=body,
        source_file=str(path),
    )


def load_subagent_defs(*dirs: Path) -> dict[str, SubagentDef]:
    """Load agents/*.md from specified directories and return a name → SubagentDef map.

    Parameters
    ----------
    *dirs:
        List of directories to search. Defaults to _DEFAULT_AGENT_DIRS if omitted.

    Returns
    -------
    dict[name, SubagentDef]
    """
    search_dirs = list(dirs) if dirs else list(_DEFAULT_AGENT_DIRS)
    result: dict[str, SubagentDef] = {}
    for d in search_dirs:
        if not d.is_dir():
            continue
        for md_file in sorted(d.glob("*.md")):
            if md_file.name.upper() == "README.MD":
                continue
            try:
                defn = _parse_agent_md(md_file)
                if defn.name not in result:
                    result[defn.name] = defn
            except SubagentLoadError as exc:
                log.warning("Subagent load error (%s): %s", md_file, exc)
    return result


# ---------------------------------------------------------------------------
# Isolated context execution
# ---------------------------------------------------------------------------

# Track nested spawn depth (passed as context parameter instead of threadlocal)
_MAX_DEPTH = 2


@dataclass
class SubagentRunResult:
    """Subagent execution result.

    Attributes
    ----------
    name:
        Name of the executed subagent.
    raw_output:
        Raw text output received from the backend.
    structured:
        Parsed structured dictionary (when JSON parsing succeeds).
    verify_status:
        Orchestrator verification result.
    warnings:
        List of subagent + verification warnings.
    """

    name: str
    raw_output: str
    structured: dict[str, Any] = field(default_factory=dict)
    verify_status: str = "unknown"
    warnings: list[str] = field(default_factory=list)


def _parse_structured_output(text: str) -> dict[str, Any]:
    """Extract JSON structured output from text.

    Tries JSON code blocks (```json ... ```) or naked JSON.
    Returns empty dict on parse failure.
    """
    # Extract ```json ... ``` block
    code_block_match = re.search(r"```json\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try naked JSON (first '{' to last '}')
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# SubagentRunner
# ---------------------------------------------------------------------------


class SubagentRunner:
    """Subagent pool executor.

    Parameters
    ----------
    defs:
        name → SubagentDef mapping (loaded via ``load_subagent_defs()``).
    backend:
        LLMBackend instance.
    verifier:
        Verifier instance (uses default quick_verify if None).
    """

    def __init__(
        self,
        defs: dict[str, SubagentDef],
        backend: Any,  # LLMBackend (Any to avoid circular import)
        verifier: Verifier | None = None,
    ) -> None:
        self._defs = defs
        self._backend = backend
        self._verifier = verifier or Verifier(allow_llm_judge=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        name: str,
        task: str,
        *,
        depth: int = 0,
        extra_context: str = "",
    ) -> dict[str, Any]:
        """Execute a subagent and return the structured result.

        Parameters
        ----------
        name:
            Name of the subagent to execute.
        task:
            Task prompt string.
        depth:
            Current nesting depth (orchestrator = 0).
        extra_context:
            JIT context to append to the system prompt.

        Returns
        -------
        Structured result dict — minimum {'status', 'warnings'}.

        Raises
        ------
        ValueError:
            Subagent name not found or depth exceeded.
        """
        if depth >= _MAX_DEPTH:
            raise ValueError(
                f"Subagent nesting depth exceeded: maximum {_MAX_DEPTH} levels. "
                f"Current depth={depth}, agent='{name}'"
            )
        defn = self._defs.get(name)
        if defn is None:
            raise ValueError(f"Subagent '{name}' not found. Registered list: {sorted(self._defs)}")

        raw_output = self._execute(defn, task, extra_context=extra_context)
        structured = _parse_structured_output(raw_output)

        # Inject default structure on parse failure
        if not structured:
            structured = {
                "status": "partial",
                "raw": raw_output,
                "warnings": ["Failed to parse structured JSON output — returning raw text."],
            }

        # 4-layer verification
        vr = self._verifier.verify(structured, is_quantitative=True)
        run_result = SubagentRunResult(
            name=name,
            raw_output=raw_output,
            structured=structured,
            verify_status=vr.status.value,
            warnings=list(structured.get("warnings") or []) + vr.warnings,
        )
        log.debug(
            "Subagent '%s' completed: verify_status=%s",
            name,
            run_result.verify_status,
        )

        # Reflect verification status in structured result
        out = dict(structured)
        out["_verify_status"] = run_result.verify_status
        out["_warnings"] = run_result.warnings
        return out

    def available(self) -> list[str]:
        """Return the list of registered subagent names."""
        return sorted(self._defs)

    def get_def(self, name: str) -> SubagentDef | None:
        """Look up a subagent definition by name."""
        return self._defs.get(name)

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    def _execute(
        self,
        defn: SubagentDef,
        task: str,
        *,
        extra_context: str = "",
    ) -> str:
        """Execute a subagent in an isolated context and return the raw text."""
        from maglab.llm.base import Message, Role  # deferred import

        system = defn.system_prompt
        if extra_context:
            system = system + f"\n\n## JIT Context\n\n{extra_context}"

        messages = [
            Message(role=Role.USER, content=task),
        ]

        # Model selection
        model = self._resolve_model(defn.model)
        try:
            # Isolated: insert system prompt before the first message
            full_messages = [
                Message(role=Role.SYSTEM, content=system),
                *messages,
            ]
            response = self._backend.complete(
                full_messages,
                model=model,
                max_tokens=4096,
            )
            return response.content or ""
        except Exception as exc:  # noqa: BLE001
            log.warning("Subagent '%s' backend error: %s", defn.name, exc)
            return json.dumps(
                {
                    "status": "failed",
                    "warnings": [f"Backend error: {exc}"],
                }
            )

    def _resolve_model(self, model_tier: str) -> str | None:
        """Convert a model tier string to an actual model identifier."""
        tier_map: dict[str, str] = {
            "opus": "claude-opus-4-7",
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5",
            "inherit": "",
        }
        resolved = tier_map.get(model_tier.lower(), model_tier)
        return resolved if resolved else None
