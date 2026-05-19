"""Tool call abstraction — schema definition, call request and result types (provider-neutral).

§5.16, §5.18: @tool decorator, tool registry, readOnlyHint · destructiveHint.

This module defines the schemas for tools the LLM can request, and represents
tool call requests and results as provider-neutral types.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any, get_type_hints

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool annotation hints (§5.8 autonomy gate integration)
# ---------------------------------------------------------------------------


class ToolHints(BaseModel):
    """Tool hints — consumed by the autonomy gate."""

    # True means no side effects → Tier 0 auto-execution allowed
    read_only: bool = False
    # True means irreversible operation → Tier 2+ human approval required
    destructive: bool = False
    # True means external network call involved
    network: bool = False


# ---------------------------------------------------------------------------
# Tool definition data structure
# ---------------------------------------------------------------------------


class ToolDefinition(BaseModel):
    """JSON Schema definition for a single tool."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )
    hints: ToolHints = Field(default_factory=ToolHints)

    def to_openai_dict(self) -> dict[str, Any]:
        """Convert to an OpenAI / litellm format tool dictionary."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_dict(self) -> dict[str, Any]:
        """Convert to an Anthropic Messages API format tool dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


# ---------------------------------------------------------------------------
# Tool call request and result
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    """A single tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """Tool execution result."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False
    # Execution time in seconds
    elapsed_sec: float | None = None


# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------

# Tool registry: name → (function, ToolDefinition)
_REGISTRY: dict[str, tuple[Callable[..., Any], ToolDefinition]] = {}


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    read_only: bool = False,
    destructive: bool = False,
    network: bool = False,
) -> Any:
    """Tool registration decorator.

    Registers a function as a tool that the LLM can call.  Automatically
    generates a JSON Schema from the function's docstring and type hints.

    Usage::

        @tool(read_only=True)
        def physics_compute(formula: str, params: dict) -> str:
            \"\"\"Compute a physics formula.\"\"\"
            ...

        @tool
        def run_simulation(config: str) -> str:
            \"\"\"Run a simulation.\"\"\"
            ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        tool_desc = description or (inspect.getdoc(fn) or "").split("\n")[0]

        params_schema = _build_json_schema(fn)
        hints = ToolHints(read_only=read_only, destructive=destructive, network=network)
        defn = ToolDefinition(
            name=tool_name,
            description=tool_desc,
            parameters=params_schema,
            hints=hints,
        )
        _REGISTRY[tool_name] = (fn, defn)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        # Attach tool metadata to the function
        wrapper.__tool_definition__ = defn  # type: ignore[attr-defined]
        return wrapper

    if func is not None:
        # @tool form (no arguments)
        return decorator(func)
    # @tool(...) form
    return decorator


def _build_json_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    """Generate a JSON Schema from a function signature.

    Supported types: str, int, float, bool, list, dict, Any.
    None/Optional is treated as nullable string.
    """
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []

    _type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        py_type = hints.get(param_name, Any)
        # Unwrap Optional[X]
        origin = getattr(py_type, "__origin__", None)
        args = getattr(py_type, "__args__", None)
        if origin is type(None):
            json_type = "string"
        elif origin is not None and args:
            # Union[X, None] pattern
            non_none = [a for a in args if a is not type(None)]
            json_type = _type_map.get(non_none[0], "string") if non_none else "string"
        else:
            json_type = _type_map.get(py_type, "string")

        prop: dict[str, Any] = {"type": json_type}

        # Parameters without a default value are required
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

        properties[param_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# ---------------------------------------------------------------------------
# Registry public API
# ---------------------------------------------------------------------------


def get_registered_tools() -> list[ToolDefinition]:
    """Return the list of registered tool definitions."""
    return [defn for _, defn in _REGISTRY.values()]


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Call a registered tool by name.

    Args:
        name: Tool name.
        arguments: Tool argument dictionary.

    Returns:
        Tool return value.

    Raises:
        KeyError: When the tool name is not registered.
        ValueError: When the argument schema does not match.
    """
    if name not in _REGISTRY:
        raise KeyError(f"Unregistered tool: {name!r}. Registered tools: {list(_REGISTRY)}")
    fn, defn = _REGISTRY[name]
    return fn(**arguments)


def is_allowed(name: str, allowlist: set[str] | None = None) -> bool:
    """Check whether a tool is in the allowlist.

    All tools are allowed when allowlist is None.

    Args:
        name: Tool name.
        allowlist: Set of allowed tool names.

    Returns:
        True if allowed.
    """
    if allowlist is None:
        return True
    return name in allowlist


def get_tool_definition(name: str) -> ToolDefinition | None:
    """Look up a tool definition by name."""
    entry = _REGISTRY.get(name)
    return entry[1] if entry else None
