"""Tool calling for backends with no native tool API.

The delegated CLI backends accepted a `tools` argument and dropped it, so
`tool_calls` was always empty. That did not merely lose a convenience: the
orchestrator's tool loop never ran, which meant the hook layer, the physics
oracle and the autonomy gate never saw a call, and the CLI answered from its own
filesystem tools instead of MagLab's deterministic ones.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from maglab.llm.backends.delegated_cli import DelegatedCLIBackend
from maglab.llm.backends.tool_bridge import (
    build_tool_instructions,
    extract_tool_calls,
    strip_tool_calls,
)
from maglab.llm.base import Message, Role

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "literature_search",
            "description": "Search scholarly literature by query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}},
                "required": ["query"],
            },
        },
    }
]


class TestInstructions:
    def test_names_every_tool(self) -> None:
        text = build_tool_instructions(TOOLS)
        assert "literature_search(" in text

    def test_marks_required_versus_optional_arguments(self) -> None:
        text = build_tool_instructions(TOOLS)
        assert "query: string" in text
        assert "max_results?: integer" in text

    def test_empty_tool_list_adds_nothing(self) -> None:
        assert build_tool_instructions([]) == ""

    def test_states_that_tools_are_the_source_of_numbers(self) -> None:
        """The instruction exists to stop the model computing values itself."""
        assert "do not compute such values yourself" in build_tool_instructions(TOOLS)

    def test_stays_compact_for_the_full_registry(self) -> None:
        from maglab.llm import tools as registry

        definitions = [t.to_openai_dict() for t in registry.get_registered_tools()]
        text = build_tool_instructions(definitions)

        assert len(definitions) > 30
        assert len(text) < 20_000, "catalogue would dominate the prompt budget"


class TestExtraction:
    def test_parses_a_tool_call(self) -> None:
        reply = (
            "Searching now.\n\n"
            "```maglab-tool-call\n"
            '{"name": "literature_search", "arguments": {"query": "spintronics"}}\n'
            "```"
        )
        calls = extract_tool_calls(reply)

        assert len(calls) == 1
        assert calls[0].name == "literature_search"
        assert calls[0].arguments == {"query": "spintronics"}

    def test_parses_several_calls(self) -> None:
        reply = (
            '```maglab-tool-call\n{"name": "a", "arguments": {}}\n```\n'
            '```maglab-tool-call\n{"name": "b", "arguments": {}}\n```'
        )
        assert [c.name for c in extract_tool_calls(reply)] == ["a", "b"]

    def test_each_call_gets_an_id(self) -> None:
        reply = '```maglab-tool-call\n{"name": "a", "arguments": {}}\n```'
        assert extract_tool_calls(reply)[0].id

    @pytest.mark.parametrize(
        "reply",
        [
            "plain prose with no block",
            "```maglab-tool-call\n{broken json\n```",
            "```maglab-tool-call\n[1, 2, 3]\n```",
            '```maglab-tool-call\n{"arguments": {}}\n```',
            '```maglab-tool-call\n{"name": "  "}\n```',
            '```json\n{"name": "a", "arguments": {}}\n```',
        ],
    )
    def test_malformed_or_unrelated_content_yields_no_calls(self, reply: str) -> None:
        """A bad block degrades to prose — the pre-bridge behaviour — never an exception."""
        assert extract_tool_calls(reply) == []

    def test_non_dict_arguments_become_empty(self) -> None:
        reply = '```maglab-tool-call\n{"name": "a", "arguments": "oops"}\n```'
        assert extract_tool_calls(reply)[0].arguments == {}

    def test_strip_removes_the_block(self) -> None:
        reply = 'Answer.\n```maglab-tool-call\n{"name": "a", "arguments": {}}\n```'
        assert strip_tool_calls(reply) == "Answer."


class TestDelegatedBackendIntegration:
    def _backend(self) -> DelegatedCLIBackend:
        return DelegatedCLIBackend(cli="codex", timeout=30)

    def _run(self, backend: DelegatedCLIBackend, stdout: str, **kwargs):
        completed = SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        with (
            patch.object(backend, "_find_executable", return_value="/usr/bin/codex"),
            patch(
                "maglab.llm.backends.delegated_cli.subprocess.run", return_value=completed
            ) as run,
        ):
            response = backend.complete([Message(role=Role.USER, content="hi")], **kwargs)
        return response, run

    def test_tools_reach_the_prompt(self) -> None:
        _resp, run = self._run(self._backend(), "ok", tools=TOOLS)
        command = run.call_args[0][0]
        assert any("literature_search(" in str(part) for part in command)

    def test_no_tools_means_no_injected_catalogue(self) -> None:
        _resp, run = self._run(self._backend(), "ok")
        command = run.call_args[0][0]
        assert not any("MAGLAB TOOLS" in str(part) for part in command)

    def test_a_tool_call_reply_becomes_tool_calls(self) -> None:
        reply = (
            "Let me search.\n"
            "```maglab-tool-call\n"
            '{"name": "literature_search", "arguments": {"query": "spintronics"}}\n'
            "```"
        )
        response, _run = self._run(self._backend(), reply, tools=TOOLS)

        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "literature_search"
        assert response.stop_reason == "tool_use"
        assert "maglab-tool-call" not in (response.content or "")

    def test_prose_reply_is_unchanged(self) -> None:
        response, _run = self._run(self._backend(), "Just an answer.", tools=TOOLS)

        assert response.tool_calls == []
        assert "Just an answer." in (response.content or "")

    def test_tool_calls_are_executable_by_the_registry(self) -> None:
        """The parsed call must be shaped for the orchestrator's existing loop."""
        from maglab.llm.tools import get_tool_definition

        reply = (
            "```maglab-tool-call\n"
            '{"name": "physics_compute", "arguments": '
            '{"formula": "exchange_length", "params": {"A": 1.3e-11, "Ms": 800000.0}}}\n'
            "```"
        )
        response, _run = self._run(self._backend(), reply, tools=TOOLS)
        call = response.tool_calls[0]

        assert get_tool_definition(call.name) is not None
        from maglab.llm.tools import call_tool

        result = call_tool(call.name, call.arguments)
        assert json.dumps(result)  # serialisable, i.e. usable as a tool result
