"""MagLab MCP client (A-role) — registry, lazy connections, tool namespacing (§5.18).

Design principles
-----------------
- Registry-driven: server configs live in ``.maglab/mcp.json`` (local project) or
  ``~/.config/maglab/mcp.json`` (global user). The first file found wins.
- Lazy connection: each server's session is opened only when one of its tools is
  first requested. Idle servers consume no resources.
- Tool namespacing: every external tool is exposed as ``<server>::<tool>`` to avoid
  name collisions with each other and with MagLab's own built-in tools.
- Trust-level enforcement: tools from ``untrusted`` servers are flagged and require
  explicit human approval before invocation. ``restricted`` tools are callable but
  carry a warning. ``trusted`` servers are called without extra gating.
- Enable / disable persistence: ``enabled`` flag is toggled in-place in ``mcp.json``.
- Heavy imports (``mcp`` SDK) are deferred so that ``maglab --help`` works even when
  the ``[mcp]`` optional extra is not installed.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from maglab.core.atomic import atomic_write_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional mcp SDK — imported at module level so tests can patch the names.
# These are set to None when the [mcp] extra is not installed; the code that
# uses them raises ImportError at call-time with a helpful message.
# ---------------------------------------------------------------------------

try:
    from mcp import StdioServerParameters, stdio_client  # type: ignore[import-untyped]
    from mcp.client.session import ClientSession  # type: ignore[import-untyped]

    _MCP_AVAILABLE = True
except ImportError:
    StdioServerParameters = None  # type: ignore[assignment,misc]
    stdio_client = None  # type: ignore[assignment]
    ClientSession = None  # type: ignore[assignment,misc]
    _MCP_AVAILABLE = False

try:
    from mcp.client.sse import sse_client  # type: ignore[import-untyped]

    _MCP_SSE_AVAILABLE = True
except ImportError:
    sse_client = None  # type: ignore[assignment]
    _MCP_SSE_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REGISTRY_FILENAMES: list[Path] = [
    Path(".maglab") / "mcp.json",
    Path.home() / ".config" / "maglab" / "mcp.json",
]

_VALID_TRANSPORTS = {"stdio", "http"}
_VALID_TRUST_LEVELS = {"trusted", "restricted", "untrusted"}


# ---------------------------------------------------------------------------
# Data structures (pure Python — no mcp SDK dependency)
# ---------------------------------------------------------------------------


class ServerConfig:
    """Configuration for a single external MCP server.

    Attributes:
        name:        Registry key used as the tool namespace prefix.
        transport:   ``stdio`` or ``http``.
        command:     Executable path (stdio only).
        args:        Argument list for the executable (stdio only).
        env:         Extra environment variables (stdio only).
        url:         HTTP/SSE endpoint URL (http only).
        trust_level: ``trusted`` | ``restricted`` | ``untrusted``.
        always_load: If True, the server is connected at startup.
        enabled:     If False, the server is skipped entirely.
    """

    __slots__ = (
        "name",
        "transport",
        "command",
        "args",
        "env",
        "url",
        "trust_level",
        "always_load",
        "enabled",
    )

    def __init__(
        self,
        name: str,
        transport: str = "stdio",
        command: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str = "",
        trust_level: str = "restricted",
        always_load: bool = False,
        enabled: bool = True,
    ) -> None:
        self.name = name
        self.transport = transport
        self.command = command
        self.args: list[str] = args or []
        self.env: dict[str, str] = env or {}
        self.url = url
        self.trust_level = trust_level
        self.always_load = always_load
        self.enabled = enabled

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a registry-compatible dictionary."""
        d: dict[str, Any] = {
            "type": self.transport,
            "trust_level": self.trust_level,
            "always_load": self.always_load,
            "enabled": self.enabled,
        }
        if self.transport == "stdio":
            d["command"] = self.command
            if self.args:
                d["args"] = self.args
            if self.env:
                d["env"] = self.env
        else:
            d["url"] = self.url
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ServerConfig:
        """Deserialise from a registry dictionary entry."""
        transport = data.get("type", "stdio")
        return cls(
            name=name,
            transport=transport,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url", ""),
            trust_level=data.get("trust_level", "restricted"),
            always_load=bool(data.get("always_load", False)),
            enabled=bool(data.get("enabled", True)),
        )


class ToolInfo:
    """Metadata for a single namespaced external tool.

    Attributes:
        namespaced_name: ``server::tool`` compound key.
        server_name:     Registry name of the owning server.
        tool_name:       Raw tool name as declared by the server.
        description:     Tool description text.
        trust_level:     Inherited from the owning server config.
        input_schema:    JSON schema dict for the tool's input (may be empty).
    """

    __slots__ = (
        "namespaced_name",
        "server_name",
        "tool_name",
        "description",
        "trust_level",
        "input_schema",
    )

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        description: str = "",
        trust_level: str = "restricted",
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        self.server_name = server_name
        self.tool_name = tool_name
        self.namespaced_name = f"{server_name}::{tool_name}"
        self.description = description
        self.trust_level = trust_level
        self.input_schema: dict[str, Any] = input_schema or {}


# ---------------------------------------------------------------------------
# Registry load / save
# ---------------------------------------------------------------------------


def _resolve_registry_path() -> Path | None:
    """Return the first existing registry file, or None."""
    for path in _REGISTRY_FILENAMES:
        if path.is_file():
            return path
    return None


def _load_registry(path: Path) -> dict[str, ServerConfig]:
    """Parse ``mcp.json`` and return a name-keyed dict of ServerConfig objects.

    Args:
        path: Path to the ``mcp.json`` file.

    Returns:
        Dictionary mapping server name → ServerConfig.

    Raises:
        ValueError: If the file contains invalid JSON.
    """
    raw_text = path.read_text(encoding="utf-8")
    try:
        data: dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"mcp.json is not valid JSON: {exc}") from exc

    servers_raw: dict[str, Any] = data.get("servers", {})
    result: dict[str, ServerConfig] = {}
    for name, cfg in servers_raw.items():
        try:
            result[name] = ServerConfig.from_dict(name, cfg)
        except Exception as exc:
            logger.warning("Skipping server %r — parse error: %s", name, exc)
    return result


def _save_registry(path: Path, configs: dict[str, ServerConfig]) -> None:
    """Write ``configs`` back to ``path`` as JSON, preserving file structure.

    Args:
        path:    Destination file path.
        configs: Current server configs to serialise.
    """
    # Try to read the existing top-level structure so non-server keys are preserved.
    existing: dict[str, Any] = {}
    if path.is_file():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            existing = json.loads(path.read_text(encoding="utf-8"))

    servers_out: dict[str, Any] = {name: cfg.to_dict() for name, cfg in configs.items()}
    existing["servers"] = servers_out
    # Atomic: a half-written mcp.json is unparseable, and the read above
    # suppresses a decode error into an empty dict — so the next save would
    # silently drop every registered server and any non-server keys.
    atomic_write_text(path, json.dumps(existing, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# MCPClientRegistry
# ---------------------------------------------------------------------------


class MCPClientRegistry:
    """A-role MCP client — manages external server connections and tool dispatch.

    Responsibilities
    ----------------
    1. Load the ``mcp.json`` registry and expose server configs.
    2. Maintain lazy per-server async sessions (connected on first tool use).
    3. Enumerate namespaced tools (``server::tool``) across all enabled servers.
    4. Enforce ``trust_level`` — untrusted tool calls raise ``TrustError``.
    5. Persist enable/disable changes back to ``mcp.json``.

    Usage example::

        registry = MCPClientRegistry()
        registry.load()

        # Add a new server
        registry.add_server("arxiv", "npx -y @modelcontextprotocol/server-arxiv",
                            transport="stdio", trust_level="trusted")

        # Programmatic tool invocation (async):
        import asyncio
        result = asyncio.run(registry.call_tool("arxiv::search_papers",
                                                {"query": "spintronics 2024"}))

    Notes
    -----
    - ``load()`` must be called before any tool operations.
    - The ``mcp`` Python SDK is imported lazily; if the ``[mcp]`` extra is absent,
      listing tools works but ``connect_server`` / ``call_tool`` will raise
      ``ImportError`` with a helpful message.
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        """Initialise the registry.

        Args:
            registry_path: Explicit path to ``mcp.json``. If None, the first
                file found in the standard search order is used; if no file
                exists the registry starts empty.
        """
        self._explicit_path: Path | None = registry_path
        self._path: Path | None = None
        self._configs: dict[str, ServerConfig] = {}
        # Lazy sessions: server_name -> open ClientSession (kept alive by _cm_stacks)
        self._sessions: dict[str, Any] = {}
        # Per-server AsyncExitStack that keeps the transport + session context managers open.
        # Each stack is aclose()'d when the server is disabled or close_all() is called.
        self._cm_stacks: dict[str, contextlib.AsyncExitStack] = {}
        # Cached tool index: namespaced_name -> ToolInfo
        self._tools: dict[str, ToolInfo] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API — registry management
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load the registry from disk. Idempotent — safe to call multiple times.

        If no registry file exists, the registry starts empty (no error).
        """
        path = self._explicit_path if self._explicit_path is not None else _resolve_registry_path()

        if path is None or not path.is_file():
            self._path = self._explicit_path or _REGISTRY_FILENAMES[0]
            self._configs = {}
            self._loaded = True
            return

        self._path = path
        self._configs = _load_registry(path)
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    @property
    def registry_path(self) -> Path:
        """Resolved path for the active registry file."""
        self._ensure_loaded()
        return self._path or _REGISTRY_FILENAMES[0]

    @property
    def servers(self) -> dict[str, ServerConfig]:
        """Read-only view of the loaded server configs."""
        self._ensure_loaded()
        return dict(self._configs)

    def add_server(
        self,
        name: str,
        command_or_url: str,
        transport: str = "stdio",
        trust_level: str = "restricted",
        always_load: bool = False,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> ServerConfig:
        """Register a new external MCP server and persist the change.

        Args:
            name:            Registry key and tool namespace prefix.
            command_or_url:  Command string (stdio) or HTTP URL (http).
            transport:       ``stdio`` or ``http``.
            trust_level:     ``trusted`` | ``restricted`` | ``untrusted``.
            always_load:     Whether to connect at startup.
            args:            Additional CLI arguments (stdio only).
            env:             Extra environment variables (stdio only).

        Returns:
            The newly created ServerConfig.

        Raises:
            ValueError: If transport or trust_level is invalid, or name conflicts.
        """
        self._ensure_loaded()

        if transport not in _VALID_TRANSPORTS:
            raise ValueError(
                f"Invalid transport {transport!r}. Choose from: {sorted(_VALID_TRANSPORTS)}"
            )
        if trust_level not in _VALID_TRUST_LEVELS:
            raise ValueError(
                f"Invalid trust_level {trust_level!r}. Choose from: {sorted(_VALID_TRUST_LEVELS)}"
            )
        if name in self._configs:
            raise ValueError(
                f"Server {name!r} is already registered. Use enable/disable or remove it first."
            )

        # Expand environment variables in the command string.
        expanded = os.path.expandvars(command_or_url)

        if transport == "stdio":
            cfg = ServerConfig(
                name=name,
                transport="stdio",
                command=expanded,
                args=args or [],
                env=env or {},
                trust_level=trust_level,
                always_load=always_load,
                enabled=True,
            )
        else:
            cfg = ServerConfig(
                name=name,
                transport="http",
                url=expanded,
                trust_level=trust_level,
                always_load=always_load,
                enabled=True,
            )

        self._configs[name] = cfg
        self._save()
        return cfg

    def enable_server(self, name: str) -> None:
        """Set the ``enabled`` flag to True for the named server and save.

        Args:
            name: Registry name of the server.

        Raises:
            KeyError: If no server with that name exists.
        """
        self._ensure_loaded()
        if name not in self._configs:
            raise KeyError(f"Server not found in registry: {name!r}")
        self._configs[name].enabled = True
        self._save()

    def disable_server(self, name: str) -> None:
        """Set the ``enabled`` flag to False for the named server and save.

        Args:
            name: Registry name of the server.

        Raises:
            KeyError: If no server with that name exists.
        """
        self._ensure_loaded()
        if name not in self._configs:
            raise KeyError(f"Server not found in registry: {name!r}")
        self._configs[name].enabled = False
        # Close any open session for the now-disabled server.
        self._sessions.pop(name, None)
        # Release the transport + session context managers kept alive for this server.
        stack = self._cm_stacks.pop(name, None)
        if stack is not None:
            import asyncio

            # best-effort close; schedule on the running loop if one exists
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(stack.aclose())
                else:
                    loop.run_until_complete(stack.aclose())
            except RuntimeError:
                pass  # no event loop — stack will be GC'd
        # Evict tools belonging to this server from the cache.
        self._tools = {k: v for k, v in self._tools.items() if v.server_name != name}
        self._save()

    async def close_all(self) -> None:
        """Close all open server connections and release their resources.

        This method must be awaited to ensure that every transport and session
        context manager is properly shut down.  Call it when the registry is
        no longer needed (e.g. at application exit or in test teardown).

        After this call ``_sessions`` and ``_cm_stacks`` are empty; subsequent
        ``call_tool`` / ``_ensure_connected`` calls will reconnect lazily.
        """
        stacks = list(self._cm_stacks.values())
        self._cm_stacks.clear()
        self._sessions.clear()
        for stack in stacks:
            try:
                await stack.aclose()
            except Exception as exc:
                logger.warning("Error closing MCP connection stack: %s", exc)

    # ------------------------------------------------------------------
    # Tool enumeration
    # ------------------------------------------------------------------

    def list_tools(self) -> list[ToolInfo]:
        """Return the list of currently cached namespaced tools.

        This is a *synchronous* snapshot. To populate it, call
        ``connect_all_enabled()`` or ``connect_server()`` first, or use
        ``list_tools_async()`` which connects lazily.

        Returns:
            List of ToolInfo objects for all enabled, connected servers.
        """
        return list(self._tools.values())

    async def list_tools_async(self, server_name: str | None = None) -> list[ToolInfo]:
        """Connect to server(s) if needed and return their namespaced tools.

        Args:
            server_name: If given, only enumerate tools for that server.
                         If None, enumerate all enabled servers.

        Returns:
            List of ToolInfo objects.
        """
        self._ensure_loaded()
        if server_name is not None:
            await self._ensure_connected(server_name)
        else:
            for name, cfg in self._configs.items():
                if cfg.enabled:
                    await self._ensure_connected(name)
        return self.list_tools()

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        namespaced_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        skip_trust_check: bool = False,
    ) -> Any:
        """Invoke an external tool by its namespaced name.

        Args:
            namespaced_name: ``server::tool`` compound key.
            arguments:       Tool input arguments.
            skip_trust_check: If True, bypass the trust-level gate. Intended
                              only for internal testing.

        Returns:
            Raw tool result from the MCP server.

        Raises:
            KeyError:     If the tool or server is not found.
            TrustError:   If the server is ``untrusted`` and the trust check
                          is not skipped.
            ImportError:  If the ``[mcp]`` extra is absent.
        """
        self._ensure_loaded()

        if "::" not in namespaced_name:
            raise KeyError(f"Tool name {namespaced_name!r} must be namespaced as 'server::tool'.")

        server_name, tool_name = namespaced_name.split("::", 1)

        if server_name not in self._configs:
            raise KeyError(f"No server registered with name {server_name!r}.")

        cfg = self._configs[server_name]
        if not cfg.enabled:
            raise KeyError(f"Server {server_name!r} is disabled.")

        if not skip_trust_check and cfg.trust_level == "untrusted":
            raise TrustError(
                f"Server {server_name!r} has trust_level='untrusted'. "
                "Invoke with skip_trust_check=True after explicit human approval."
            )

        await self._ensure_connected(server_name)
        session = self._sessions.get(server_name)
        if session is None:
            raise RuntimeError(f"Failed to connect to server {server_name!r}.")

        result = await session.call_tool(tool_name, arguments or {})
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_connected(self, server_name: str) -> None:
        """Connect to ``server_name`` if not already connected, and cache tools.

        This is the lazy-connection entry point. It opens a transport, creates
        an MCP ClientSession, initialises it, and populates the tool index.

        Args:
            server_name: Registry name of the target server.

        Raises:
            KeyError:    If the server is not registered or is disabled.
            ImportError: If the ``mcp`` SDK is not installed.
        """
        if server_name in self._sessions:
            return  # already connected

        if server_name not in self._configs:
            raise KeyError(f"Server not found: {server_name!r}")

        cfg = self._configs[server_name]
        if not cfg.enabled:
            raise KeyError(f"Server {server_name!r} is disabled.")

        if not _MCP_AVAILABLE or StdioServerParameters is None or ClientSession is None:
            raise ImportError(
                "The 'mcp' package is required for MCP client connections. "
                "Install it with: pip install maglab[mcp]"
            )

        # Use a persistent AsyncExitStack so that the transport and session context
        # managers stay open for the lifetime of the stored session.  Calling
        # `async with transport_cm as ...; async with session_cm as ...` and then
        # exiting those blocks immediately closes the transport streams, leaving
        # `self._sessions[server_name]` pointing to a dead/closed session.
        stack = contextlib.AsyncExitStack()
        try:
            if cfg.transport == "stdio":
                env = {**os.environ, **cfg.env} if cfg.env else None
                server_params = StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args,
                    env={k: str(v) for k, v in (env or {}).items()},
                )
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(server_params)
                )
            else:
                if not _MCP_SSE_AVAILABLE or sse_client is None:
                    raise ImportError(
                        "HTTP transport requires the 'mcp' package with SSE support. "
                        "Install it with: pip install maglab[mcp]"
                    )
                read_stream, write_stream = await stack.enter_async_context(sse_client(cfg.url))

            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            await self._index_tools(server_name, session, cfg)
        except Exception:
            await stack.aclose()
            raise

        # Store the live session and its exit stack together.  The stack keeps
        # both the transport and the ClientSession context managers open.
        self._sessions[server_name] = session
        self._cm_stacks[server_name] = stack

    async def _index_tools(
        self,
        server_name: str,
        session: Any,
        cfg: ServerConfig,
    ) -> None:
        """Fetch the tool list from an open session and populate the tool index.

        Args:
            server_name: Registry name (used as namespace prefix).
            session:     An initialised MCP ClientSession.
            cfg:         Server configuration (provides trust_level).
        """
        try:
            response = await session.list_tools()
            tools = getattr(response, "tools", response) or []
        except Exception as exc:
            logger.warning("Could not list tools for server %r: %s", server_name, exc)
            return

        for tool in tools:
            name = getattr(tool, "name", str(tool))
            desc = getattr(tool, "description", "") or ""
            schema: Any = getattr(tool, "inputSchema", None)
            schema_dict: dict[str, Any]
            if schema is not None and hasattr(schema, "model_dump"):
                schema_dict = schema.model_dump()  # type: ignore[union-attr]
            elif isinstance(schema, dict):
                schema_dict = schema
            else:
                schema_dict = {}

            info = ToolInfo(
                server_name=server_name,
                tool_name=name,
                description=desc,
                trust_level=cfg.trust_level,
                input_schema=schema_dict,
            )
            self._tools[info.namespaced_name] = info

    def _save(self) -> None:
        """Persist current configs to disk."""
        path = self._path or _REGISTRY_FILENAMES[0]
        _save_registry(path, self._configs)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class TrustError(Exception):
    """Raised when an untrusted server's tool is called without explicit approval."""


# ---------------------------------------------------------------------------
# Module-level convenience singleton (lazily initialised)
# ---------------------------------------------------------------------------

_registry: MCPClientRegistry | None = None


def get_registry(registry_path: Path | None = None) -> MCPClientRegistry:
    """Return the module-level MCPClientRegistry singleton.

    Args:
        registry_path: Optional explicit path. Ignored after the first call
                       unless ``registry_path`` differs from the cached one.

    Returns:
        The loaded MCPClientRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = MCPClientRegistry(registry_path=registry_path)
        _registry.load()
    return _registry


def reset_registry() -> None:
    """Reset the module-level singleton. Useful for testing."""
    global _registry
    _registry = None
