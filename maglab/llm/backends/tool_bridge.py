"""Tool calling for backends that have no native tool API.

The delegated CLI backends drive `codex`/`claude`/`gemini` as subprocesses.
Those binaries are agents with their own tools; none of them accept an
OpenAI-style tool schema on the command line. So the orchestrator handed 42 tool
definitions to the backend and the backend dropped them, returning
``tool_calls=[]`` every time.

The effect was not a missing convenience. MagLab's whole premise is that numbers
and citations come from deterministic tools and that every tool call passes the
hook layer — deny rules, the physics oracle, the autonomy gate. With no tool
calls, none of that ran, and the CLI answered from its own filesystem tools
instead. On this backend the harness was a prompt wrapper.

This module restores the contract with a text protocol: the tool schemas are
described in the prompt, the model replies with a JSON block, and the reply is
parsed back into ``ToolCall`` objects that the orchestrator's existing loop
executes — through the hooks, exactly like the API backend.

A model that ignores the protocol simply answers in prose, which is the
behaviour that existed before. The bridge can only add capability.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from maglab.llm.base import ToolCall

# Fenced block the model is asked to emit. Deliberately distinct from plain
# ```json so ordinary JSON in an answer is never mistaken for a tool call.
_FENCE = "maglab-tool-call"
_BLOCK_RE = re.compile(rf"```{_FENCE}\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

# Tool schemas are verbose; sending all 42 in full costs more than it buys.
_MAX_DESCRIPTION_CHARS = 220


def _summarise(tool: dict[str, Any]) -> str:
    """One line per tool: name, parameters, and what it does."""
    fn = tool.get("function", tool)
    name = fn.get("name", "?")
    description = (fn.get("description") or "").strip().replace("\n", " ")
    if len(description) > _MAX_DESCRIPTION_CHARS:
        description = description[: _MAX_DESCRIPTION_CHARS - 1] + "…"
    params = fn.get("parameters", {}) or {}
    properties = params.get("properties", {}) or {}
    required = set(params.get("required", []) or [])
    rendered = ", ".join(
        f"{key}{'' if key in required else '?'}: {spec.get('type', 'any')}"
        for key, spec in properties.items()
    )
    return f"- {name}({rendered}) — {description}"


def build_tool_instructions(tools: list[dict[str, Any]]) -> str:
    """Describe the available tools and the reply format that invokes them."""
    if not tools:
        return ""
    catalogue = "\n".join(_summarise(tool) for tool in tools)
    return (
        "\n\n[MAGLAB TOOLS]\n"
        "You are running inside MagLab. These deterministic tools are available. "
        "They are the only sanctioned source of numbers, citations and figure "
        "data — do not compute such values yourself, and do not substitute your "
        "own file or shell tools for them.\n\n"
        f"{catalogue}\n\n"
        "To call one, reply with ONLY this block and nothing else:\n\n"
        f"```{_FENCE}\n"
        '{"name": "<tool name>", "arguments": {"<arg>": <value>}}\n'
        "```\n\n"
        "You will be given the result and may then call another tool or answer. "
        "When you have what you need, answer in prose with no block. "
        "Never invent a tool name that is not listed above.\n"
    )


def extract_tool_calls(text: str) -> list[ToolCall]:
    """Parse ``maglab-tool-call`` blocks out of a model reply.

    A malformed block yields no tool call rather than an exception: the reply is
    then treated as prose, which degrades to the pre-bridge behaviour instead of
    failing the turn.
    """
    calls: list[ToolCall] = []
    for match in _BLOCK_RE.finditer(text or ""):
        try:
            payload = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(
            ToolCall(id=f"bridge-{uuid.uuid4().hex[:8]}", name=name.strip(), arguments=arguments)
        )
    return calls


def strip_tool_calls(text: str) -> str:
    """Return *text* with the tool-call blocks removed."""
    return _BLOCK_RE.sub("", text or "").strip()
