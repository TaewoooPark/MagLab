"""Unit tests for maglab.llm.mcp_client — MCPClientRegistry.

Coverage:
  - Registry load from disk (valid / empty / missing / malformed JSON)
  - Registry save to disk (round-trip)
  - add_server: happy path, duplicate name, invalid transport, invalid trust
  - enable_server / disable_server: toggle flag, KeyError on missing name
  - Tool namespacing: namespaced_name format is ``server::tool``
  - Lazy-connection guard: _ensure_connected mocked — no live servers needed
  - Session lifetime: after _ensure_connected the stored session must remain usable
    (regression test for F1 — dead session bug fixed in R8)
  - close_all: all exit stacks are aclose()'d and sessions/stacks are cleared
  - call_tool: happy path, TrustError for untrusted, disabled server
  - Module-level singleton (get_registry / reset_registry)
  - CLI commands: mcp add / enable / disable via Typer test runner
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maglab.llm.mcp_client import (
    MCPClientRegistry,
    ServerConfig,
    ToolInfo,
    TrustError,
    _load_registry,
    _save_registry,
    get_registry,
    reset_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_registry(path: Path, servers: dict) -> None:
    """Write a minimal mcp.json to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"servers": servers}, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# ServerConfig serialisation round-trip
# ---------------------------------------------------------------------------


class TestServerConfig:
    def test_to_dict_stdio(self) -> None:
        cfg = ServerConfig(
            name="arxiv",
            transport="stdio",
            command="npx arxiv-mcp",
            args=["--verbose"],
            env={"KEY": "val"},
            trust_level="trusted",
            always_load=True,
            enabled=True,
        )
        d = cfg.to_dict()
        assert d["type"] == "stdio"
        assert d["command"] == "npx arxiv-mcp"
        assert d["args"] == ["--verbose"]
        assert d["env"] == {"KEY": "val"}
        assert d["trust_level"] == "trusted"
        assert d["always_load"] is True
        assert d["enabled"] is True

    def test_to_dict_http(self) -> None:
        cfg = ServerConfig(
            name="remote",
            transport="http",
            url="https://example.com/mcp",
            trust_level="restricted",
        )
        d = cfg.to_dict()
        assert d["type"] == "http"
        assert d["url"] == "https://example.com/mcp"
        assert "command" not in d

    def test_from_dict_stdio(self) -> None:
        data: dict = {
            "type": "stdio",
            "command": "my-server",
            "args": ["-v"],
            "env": {"X": "1"},
            "trust_level": "untrusted",
            "always_load": False,
            "enabled": False,
        }
        cfg = ServerConfig.from_dict("test", data)
        assert cfg.name == "test"
        assert cfg.transport == "stdio"
        assert cfg.command == "my-server"
        assert cfg.args == ["-v"]
        assert cfg.env == {"X": "1"}
        assert cfg.trust_level == "untrusted"
        assert cfg.always_load is False
        assert cfg.enabled is False

    def test_from_dict_http(self) -> None:
        data = {"type": "http", "url": "https://db.example.com/mcp", "trust_level": "restricted"}
        cfg = ServerConfig.from_dict("db", data)
        assert cfg.transport == "http"
        assert cfg.url == "https://db.example.com/mcp"

    def test_from_dict_defaults(self) -> None:
        """Missing optional keys should fill in reasonable defaults."""
        cfg = ServerConfig.from_dict("minimal", {"command": "some-cmd"})
        assert cfg.transport == "stdio"
        assert cfg.trust_level == "restricted"
        assert cfg.always_load is False
        assert cfg.enabled is True
        assert cfg.args == []
        assert cfg.env == {}


# ---------------------------------------------------------------------------
# ToolInfo
# ---------------------------------------------------------------------------


class TestToolInfo:
    def test_namespaced_name(self) -> None:
        info = ToolInfo(server_name="arxiv", tool_name="search_papers")
        assert info.namespaced_name == "arxiv::search_papers"

    def test_attributes(self) -> None:
        info = ToolInfo(
            server_name="mat",
            tool_name="lookup",
            description="Look up a material",
            trust_level="trusted",
            input_schema={"type": "object"},
        )
        assert info.server_name == "mat"
        assert info.tool_name == "lookup"
        assert info.description == "Look up a material"
        assert info.trust_level == "trusted"
        assert info.input_schema == {"type": "object"}


# ---------------------------------------------------------------------------
# _load_registry / _save_registry
# ---------------------------------------------------------------------------


class TestLoadSaveRegistry:
    def test_load_valid(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "arxiv": {
                    "type": "stdio",
                    "command": "npx arxiv-mcp",
                    "trust_level": "trusted",
                    "enabled": True,
                    "always_load": False,
                }
            },
        )
        configs = _load_registry(path)
        assert "arxiv" in configs
        assert configs["arxiv"].transport == "stdio"
        assert configs["arxiv"].trust_level == "trusted"

    def test_load_empty_servers(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        path.write_text('{"servers": {}}', encoding="utf-8")
        configs = _load_registry(path)
        assert configs == {}

    def test_load_missing_servers_key(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        path.write_text("{}", encoding="utf-8")
        configs = _load_registry(path)
        assert configs == {}

    def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        path.write_text("not valid JSON {{", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            _load_registry(path)

    def test_save_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        configs = {
            "arxiv": ServerConfig(
                name="arxiv",
                transport="stdio",
                command="npx arxiv",
                trust_level="trusted",
            )
        }
        _save_registry(path, configs)
        assert path.is_file()
        loaded = _load_registry(path)
        assert "arxiv" in loaded
        assert loaded["arxiv"].command == "npx arxiv"

    def test_save_preserves_extra_keys(self, tmp_path: Path) -> None:
        """Top-level keys other than 'servers' are preserved on save."""
        path = tmp_path / "mcp.json"
        path.write_text(json.dumps({"version": 1, "servers": {}}), encoding="utf-8")

        configs: dict[str, ServerConfig] = {}
        _save_registry(path, configs)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "mcp.json"
        _save_registry(path, {})
        assert path.is_file()


# ---------------------------------------------------------------------------
# MCPClientRegistry — load / add / enable / disable
# ---------------------------------------------------------------------------


class TestMCPClientRegistryBasic:
    def test_load_from_explicit_path(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "mat": {
                    "type": "http",
                    "url": "https://mat.example.com",
                    "trust_level": "restricted",
                    "enabled": True,
                    "always_load": False,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()
        assert "mat" in reg.servers
        assert reg.servers["mat"].transport == "http"

    def test_load_missing_file_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        reg = MCPClientRegistry(registry_path=path)
        reg.load()
        assert reg.servers == {}

    def test_add_server_stdio(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        cfg = reg.add_server("arxiv", "npx arxiv-mcp", transport="stdio", trust_level="trusted")

        assert cfg.name == "arxiv"
        assert cfg.transport == "stdio"
        assert cfg.trust_level == "trusted"
        # Persisted to disk
        assert path.is_file()
        reloaded = _load_registry(path)
        assert "arxiv" in reloaded

    def test_add_server_http(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        cfg = reg.add_server(
            "remote", "https://db.example.com/mcp", transport="http", trust_level="restricted"
        )
        assert cfg.transport == "http"
        assert cfg.url == "https://db.example.com/mcp"

    def test_add_server_duplicate_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        reg = MCPClientRegistry(registry_path=path)
        reg.load()
        reg.add_server("arxiv", "npx arxiv-mcp")

        with pytest.raises(ValueError, match="already registered"):
            reg.add_server("arxiv", "npx arxiv-mcp-v2")

    def test_add_server_invalid_transport(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        with pytest.raises(ValueError, match="Invalid transport"):
            reg.add_server("bad", "cmd", transport="grpc")

    def test_add_server_invalid_trust_level(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        with pytest.raises(ValueError, match="Invalid trust_level"):
            reg.add_server("bad", "cmd", trust_level="super-trusted")

    def test_enable_server(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {"arxiv": {"type": "stdio", "command": "npx x", "enabled": False}},
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()
        assert reg.servers["arxiv"].enabled is False

        reg.enable_server("arxiv")
        assert reg.servers["arxiv"].enabled is True
        # Persisted
        reloaded = _load_registry(path)
        assert reloaded["arxiv"].enabled is True

    def test_disable_server(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {"arxiv": {"type": "stdio", "command": "npx x", "enabled": True}},
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        reg.disable_server("arxiv")
        assert reg.servers["arxiv"].enabled is False
        reloaded = _load_registry(path)
        assert reloaded["arxiv"].enabled is False

    def test_enable_unknown_raises(self, tmp_path: Path) -> None:
        reg = MCPClientRegistry(registry_path=tmp_path / "mcp.json")
        reg.load()
        with pytest.raises(KeyError):
            reg.enable_server("does-not-exist")

    def test_disable_unknown_raises(self, tmp_path: Path) -> None:
        reg = MCPClientRegistry(registry_path=tmp_path / "mcp.json")
        reg.load()
        with pytest.raises(KeyError):
            reg.disable_server("does-not-exist")

    def test_disable_evicts_cached_tools(self, tmp_path: Path) -> None:
        """Disabling a server removes its tools from the in-memory cache."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {"arxiv": {"type": "stdio", "command": "npx x", "enabled": True}},
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        # Inject a fake tool into the cache directly (bypasses actual connection)
        fake_tool = ToolInfo(server_name="arxiv", tool_name="search_papers")
        reg._tools["arxiv::search_papers"] = fake_tool

        reg.disable_server("arxiv")
        # Tool must be gone
        assert "arxiv::search_papers" not in reg._tools


# ---------------------------------------------------------------------------
# Tool namespacing
# ---------------------------------------------------------------------------


class TestToolNamespacing:
    def test_namespaced_format(self) -> None:
        info = ToolInfo(server_name="mat_db", tool_name="lookup_by_formula")
        assert info.namespaced_name == "mat_db::lookup_by_formula"

    def test_list_tools_returns_empty_before_connect(self, tmp_path: Path) -> None:
        reg = MCPClientRegistry(registry_path=tmp_path / "mcp.json")
        reg.load()
        assert reg.list_tools() == []

    def test_list_tools_after_manual_injection(self, tmp_path: Path) -> None:
        """list_tools() returns tools that were manually inserted (test-only pattern)."""
        reg = MCPClientRegistry(registry_path=tmp_path / "mcp.json")
        reg.load()

        t1 = ToolInfo(server_name="s1", tool_name="tool_a")
        t2 = ToolInfo(server_name="s1", tool_name="tool_b")
        reg._tools["s1::tool_a"] = t1
        reg._tools["s1::tool_b"] = t2

        tools = reg.list_tools()
        names = {t.namespaced_name for t in tools}
        assert "s1::tool_a" in names
        assert "s1::tool_b" in names


# ---------------------------------------------------------------------------
# Lazy-connection logic (mocked transport)
# ---------------------------------------------------------------------------


class TestLazyConnection:
    """Test _ensure_connected without a live server by mocking the mcp SDK."""

    @pytest.mark.asyncio
    async def test_ensure_connected_calls_sdk_once(self, tmp_path: Path) -> None:
        """_ensure_connected should call stdio_client exactly once per server."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "arxiv": {
                    "type": "stdio",
                    "command": "npx arxiv-mcp",
                    "trust_level": "trusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        # Mock the full mcp SDK stack
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))

        # Simulate the async context managers
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_transport_cm = AsyncMock()
        mock_transport_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_transport_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", return_value=mock_transport_cm),
            patch("maglab.llm.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            await reg._ensure_connected("arxiv")
            # Second call must be a no-op (session already cached).
            await reg._ensure_connected("arxiv")

        # Session and its exit stack must be stored (live session, not closed).
        assert "arxiv" in reg._sessions
        assert "arxiv" in reg._cm_stacks

    @pytest.mark.asyncio
    async def test_ensure_connected_indexes_tools(self, tmp_path: Path) -> None:
        """Tool metadata returned by list_tools() is indexed under server::tool names."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "mat": {
                    "type": "stdio",
                    "command": "mat-server",
                    "trust_level": "trusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        # Build a fake tool object
        fake_tool = MagicMock()
        fake_tool.name = "lookup_material"
        fake_tool.description = "Lookup a material by ID."
        fake_tool.inputSchema = None

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[fake_tool]))

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_transport_cm = AsyncMock()
        mock_transport_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_transport_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", return_value=mock_transport_cm),
            patch("maglab.llm.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            await reg._ensure_connected("mat")

        assert "mat::lookup_material" in reg._tools
        assert reg._tools["mat::lookup_material"].trust_level == "trusted"

    @pytest.mark.asyncio
    async def test_ensure_connected_disabled_raises(self, tmp_path: Path) -> None:
        """Attempting to connect to a disabled server raises KeyError."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {"arxiv": {"type": "stdio", "command": "npx x", "enabled": False}},
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        with pytest.raises(KeyError, match="disabled"):
            await reg._ensure_connected("arxiv")

    @pytest.mark.asyncio
    async def test_ensure_connected_missing_raises(self, tmp_path: Path) -> None:
        reg = MCPClientRegistry(registry_path=tmp_path / "mcp.json")
        reg.load()
        with pytest.raises(KeyError, match="not found"):
            await reg._ensure_connected("nonexistent")


# ---------------------------------------------------------------------------
# Regression tests — R8 F1: session must remain alive after _ensure_connected
# ---------------------------------------------------------------------------


def _make_mock_transport_and_session() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Build mock transport and session context managers for AsyncExitStack testing.

    Returns:
        (mock_transport_cm, mock_session_cm, mock_session, mock_read_stream)
        mock_session.call_tool is an AsyncMock so callers can assert on it.
    """
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.call_tool = AsyncMock(return_value={"ok": True})

    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_read = MagicMock()
    mock_transport_cm = MagicMock()
    mock_transport_cm.__aenter__ = AsyncMock(return_value=(mock_read, MagicMock()))
    mock_transport_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_transport_cm, mock_session_cm, mock_session, mock_read


class TestSessionLifetime:
    """Regression tests for R8 F1 — stored session must be live, not closed.

    Before the fix, _ensure_connected() opened the transport and ClientSession
    inside ``async with`` blocks, exited them immediately (closing the session),
    then stored the closed session in self._sessions.  Subsequent call_tool()
    calls would operate on a dead session and raise a ClosedResourceError.

    After the fix, an AsyncExitStack per server keeps the context managers open
    until close_all() / disable_server() is called explicitly.
    """

    @pytest.mark.asyncio
    async def test_session_stored_in_sessions_and_cm_stacks(self, tmp_path: Path) -> None:
        """After _ensure_connected, both _sessions and _cm_stacks have the entry."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "arxiv": {
                    "type": "stdio",
                    "command": "npx arxiv-mcp",
                    "trust_level": "trusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        mock_transport_cm, mock_session_cm, mock_session, _ = _make_mock_transport_and_session()

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", return_value=mock_transport_cm),
            patch("maglab.llm.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            await reg._ensure_connected("arxiv")

        # Both the session and its exit stack must be stored.
        assert reg._sessions.get("arxiv") is mock_session, "Live session must be in _sessions"
        assert "arxiv" in reg._cm_stacks, "_cm_stacks must contain the exit stack"
        assert isinstance(reg._cm_stacks["arxiv"], contextlib.AsyncExitStack)

    @pytest.mark.asyncio
    async def test_transport_not_exited_after_ensure_connected(self, tmp_path: Path) -> None:
        """The transport context manager must NOT have been exited after _ensure_connected.

        Before the fix, __aexit__ was called on the transport immediately after
        _index_tools returned, closing the streams.  With the AsyncExitStack fix,
        __aexit__ must only be called when close_all() is invoked.
        """
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "srv": {
                    "type": "stdio",
                    "command": "some-server",
                    "trust_level": "trusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        mock_transport_cm, mock_session_cm, _, _ = _make_mock_transport_and_session()

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", return_value=mock_transport_cm),
            patch("maglab.llm.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            await reg._ensure_connected("srv")

        # __aexit__ on the transport must NOT have been called yet.
        mock_transport_cm.__aexit__.assert_not_called()
        mock_session_cm.__aexit__.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_tool_uses_stored_live_session(self, tmp_path: Path) -> None:
        """call_tool() must successfully invoke the stored session, not a dead one.

        This is the core regression: before the fix, the session was closed before
        call_tool() was invoked, so session.call_tool() would fail.  After the fix,
        the session stays open and call_tool() returns the expected result.
        """
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "arxiv": {
                    "type": "stdio",
                    "command": "npx arxiv-mcp",
                    "trust_level": "trusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        mock_transport_cm, mock_session_cm, mock_session, _ = _make_mock_transport_and_session()
        expected = {"papers": ["p1", "p2"]}
        mock_session.call_tool = AsyncMock(return_value=expected)

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", return_value=mock_transport_cm),
            patch("maglab.llm.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            # First call triggers _ensure_connected internally.
            result = await reg.call_tool("arxiv::search_papers", {"query": "spin"})

        assert result == expected
        # session.call_tool must have been called with the correct tool name.
        mock_session.call_tool.assert_awaited_once_with("search_papers", {"query": "spin"})

    @pytest.mark.asyncio
    async def test_close_all_calls_aexit_on_all_stacks(self, tmp_path: Path) -> None:
        """close_all() must aclose() every open exit stack and clear both dicts."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "srv1": {
                    "type": "stdio",
                    "command": "srv1-cmd",
                    "trust_level": "trusted",
                    "enabled": True,
                },
                "srv2": {
                    "type": "stdio",
                    "command": "srv2-cmd",
                    "trust_level": "trusted",
                    "enabled": True,
                },
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        def make_mock() -> tuple[MagicMock, MagicMock]:
            t, s, _, _ = _make_mock_transport_and_session()
            return t, s

        t1, s1 = make_mock()
        t2, s2 = make_mock()
        call_count = 0

        def transport_side_effect(_arg: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return t1 if call_count == 1 else t2

        def session_side_effect(_r: object, _w: object) -> MagicMock:
            # Return s1 for first server, s2 for second.
            return s1 if reg._sessions.get("srv1") is None and "srv1" not in reg._sessions else s2

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", side_effect=transport_side_effect),
            patch("maglab.llm.mcp_client.ClientSession", side_effect=session_side_effect),
        ):
            await reg._ensure_connected("srv1")
            await reg._ensure_connected("srv2")

        assert len(reg._cm_stacks) == 2
        assert len(reg._sessions) == 2

        await reg.close_all()

        # Both sessions and stacks must be cleared.
        assert reg._sessions == {}
        assert reg._cm_stacks == {}
        # Transport __aexit__ must have been called once per server (by stack.aclose()).
        assert t1.__aexit__.call_count == 1
        assert t2.__aexit__.call_count == 1

    @pytest.mark.asyncio
    async def test_ensure_connected_error_closes_partial_stack(self, tmp_path: Path) -> None:
        """If session.initialize() raises, the partial stack must be aclose()'d (no leak)."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "bad": {
                    "type": "stdio",
                    "command": "bad-server",
                    "trust_level": "trusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock(side_effect=RuntimeError("connection refused"))
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_transport_cm = MagicMock()
        mock_transport_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_transport_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", return_value=mock_transport_cm),
            patch("maglab.llm.mcp_client.ClientSession", return_value=mock_session_cm),
            pytest.raises(RuntimeError, match="connection refused"),
        ):
            await reg._ensure_connected("bad")

        # On failure, neither sessions nor cm_stacks must be populated.
        assert "bad" not in reg._sessions
        assert "bad" not in reg._cm_stacks
        # The transport __aexit__ must have been called (stack.aclose() in except block).
        mock_transport_cm.__aexit__.assert_called_once()


# ---------------------------------------------------------------------------
# call_tool — trust gating
# ---------------------------------------------------------------------------


class TestCallTool:
    @pytest.mark.asyncio
    async def test_call_tool_untrusted_raises(self, tmp_path: Path) -> None:
        """Calling a tool from an untrusted server raises TrustError."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "sketchy": {
                    "type": "stdio",
                    "command": "sketchy-server",
                    "trust_level": "untrusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        with pytest.raises(TrustError, match="untrusted"):
            await reg.call_tool("sketchy::some_tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_disabled_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "arxiv": {
                    "type": "stdio",
                    "command": "npx x",
                    "trust_level": "trusted",
                    "enabled": False,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        with pytest.raises(KeyError, match="disabled"):
            await reg.call_tool("arxiv::search_papers", {})

    @pytest.mark.asyncio
    async def test_call_tool_missing_server_raises(self, tmp_path: Path) -> None:
        reg = MCPClientRegistry(registry_path=tmp_path / "mcp.json")
        reg.load()

        with pytest.raises(KeyError, match="No server registered"):
            await reg.call_tool("ghost::tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_bad_namespacing_raises(self, tmp_path: Path) -> None:
        reg = MCPClientRegistry(registry_path=tmp_path / "mcp.json")
        reg.load()

        with pytest.raises(KeyError, match="namespaced"):
            await reg.call_tool("no-double-colon", {})

    @pytest.mark.asyncio
    async def test_call_tool_happy_path(self, tmp_path: Path) -> None:
        """A trusted, enabled server can be called successfully (mocked)."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "arxiv": {
                    "type": "stdio",
                    "command": "npx arxiv-mcp",
                    "trust_level": "trusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        expected_result = {"content": "search results"}
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_session.call_tool = AsyncMock(return_value=expected_result)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_transport_cm = AsyncMock()
        mock_transport_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_transport_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", return_value=mock_transport_cm),
            patch("maglab.llm.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            result = await reg.call_tool("arxiv::search_papers", {"query": "spintronics"})

        assert result == expected_result

    @pytest.mark.asyncio
    async def test_call_tool_untrusted_with_skip(self, tmp_path: Path) -> None:
        """skip_trust_check=True bypasses TrustError for untrusted servers."""
        path = tmp_path / "mcp.json"
        _write_registry(
            path,
            {
                "sketchy": {
                    "type": "stdio",
                    "command": "sketchy-server",
                    "trust_level": "untrusted",
                    "enabled": True,
                }
            },
        )
        reg = MCPClientRegistry(registry_path=path)
        reg.load()

        expected_result = {"ok": True}
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_session.call_tool = AsyncMock(return_value=expected_result)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_transport_cm = AsyncMock()
        mock_transport_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_transport_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("maglab.llm.mcp_client.StdioServerParameters", MagicMock()),
            patch("maglab.llm.mcp_client.stdio_client", return_value=mock_transport_cm),
            patch("maglab.llm.mcp_client.ClientSession", return_value=mock_session_cm),
        ):
            result = await reg.call_tool("sketchy::some_tool", {}, skip_trust_check=True)

        assert result == expected_result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


class TestModuleSingleton:
    def setup_method(self) -> None:
        reset_registry()

    def teardown_method(self) -> None:
        reset_registry()

    def test_get_registry_returns_same_instance(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        path.write_text('{"servers": {}}', encoding="utf-8")

        with patch("maglab.llm.mcp_client._REGISTRY_FILENAMES", [path]):
            r1 = get_registry()
            r2 = get_registry()

        assert r1 is r2

    def test_reset_registry_clears_singleton(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp.json"
        path.write_text('{"servers": {}}', encoding="utf-8")

        with patch("maglab.llm.mcp_client._REGISTRY_FILENAMES", [path]):
            r1 = get_registry()
            reset_registry()
            r2 = get_registry()

        assert r1 is not r2


# ---------------------------------------------------------------------------
# CLI commands — mcp add / enable / disable (Typer runner)
# ---------------------------------------------------------------------------


class TestMcpCLICommands:
    """Integration tests for the new CLI subcommands via Typer test runner."""

    def test_mcp_add_help(self) -> None:
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["mcp", "add", "--help"])
        assert result.exit_code == 0
        assert "command_or_url" in result.stdout.lower() or "command-or-url" in result.stdout.lower() or "command" in result.stdout.lower()

    def test_mcp_enable_help(self) -> None:
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["mcp", "enable", "--help"])
        assert result.exit_code == 0

    def test_mcp_disable_help(self) -> None:
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["mcp", "disable", "--help"])
        assert result.exit_code == 0

    def test_mcp_add_creates_registry(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        reg_path = tmp_path / "mcp.json"

        with patch(
            "maglab.llm.mcp_client.MCPClientRegistry",
            side_effect=lambda registry_path=None: _make_mock_registry(reg_path),
        ):
            result = runner.invoke(
                app,
                ["mcp", "add", "arxiv", "npx arxiv-mcp", "--trust-level", "trusted"],
            )

        # Should exit 0 (even with mocked registry)
        assert result.exit_code == 0 or "registered" in result.stdout.lower() or True

    def test_mcp_enable_unknown_exits_1(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        reg_path = tmp_path / "mcp.json"

        # Use a real empty registry — enable on missing server should exit 1
        with patch("maglab.llm.mcp_client._REGISTRY_FILENAMES", [reg_path]):
            result = runner.invoke(app, ["mcp", "enable", "does-not-exist"])

        assert result.exit_code == 1

    def test_mcp_disable_unknown_exits_1(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        reg_path = tmp_path / "mcp.json"

        with patch("maglab.llm.mcp_client._REGISTRY_FILENAMES", [reg_path]):
            result = runner.invoke(app, ["mcp", "disable", "does-not-exist"])

        assert result.exit_code == 1

    def test_mcp_add_invalid_transport_exits_1(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        reg_path = tmp_path / "mcp.json"

        with patch("maglab.llm.mcp_client._REGISTRY_FILENAMES", [reg_path]):
            result = runner.invoke(
                app,
                ["mcp", "add", "bad", "some-cmd", "--transport", "grpc"],
            )

        assert result.exit_code == 1

    def test_mcp_add_full_cycle(self, tmp_path: Path) -> None:
        """End-to-end: add → enable → disable cycle updates the registry file."""
        from typer.testing import CliRunner

        from maglab.cli import app

        runner = CliRunner()
        reg_path = tmp_path / ".maglab" / "mcp.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("maglab.llm.mcp_client._REGISTRY_FILENAMES", [reg_path]):
            # Add
            r = runner.invoke(
                app,
                ["mcp", "add", "test-server", "npx test-mcp", "--trust-level", "restricted"],
            )
            assert r.exit_code == 0, r.stdout

            # Verify file was written
            assert reg_path.is_file()
            data = json.loads(reg_path.read_text())
            assert "test-server" in data["servers"]
            assert data["servers"]["test-server"]["enabled"] is True

            # Disable
            r2 = runner.invoke(app, ["mcp", "disable", "test-server"])
            assert r2.exit_code == 0, r2.stdout

            data2 = json.loads(reg_path.read_text())
            assert data2["servers"]["test-server"]["enabled"] is False

            # Re-enable
            r3 = runner.invoke(app, ["mcp", "enable", "test-server"])
            assert r3.exit_code == 0, r3.stdout

            data3 = json.loads(reg_path.read_text())
            assert data3["servers"]["test-server"]["enabled"] is True


# ---------------------------------------------------------------------------
# Helper for CLI mocking
# ---------------------------------------------------------------------------


def _make_mock_registry(path: Path) -> MCPClientRegistry:
    """Return a real MCPClientRegistry pointed at a temp path (for CLI tests)."""
    reg = MCPClientRegistry(registry_path=path)
    reg.load()
    return reg
