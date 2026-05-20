"""Tool call abstraction — schema definition, call request and result types (provider-neutral).

§5.16, §5.18: @tool decorator, tool registry, readOnlyHint · destructiveHint.

This module defines the schemas for tools the LLM can request, and represents
tool call requests and results as provider-neutral types.
"""

from __future__ import annotations

import functools
import inspect
import logging
import re
from collections.abc import Callable
from pathlib import Path
from types import NoneType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

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

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        py_type = hints.get(param_name, Any)
        prop = _schema_for_type(py_type)

        # Parameters without a default value are required
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

        properties[param_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _schema_for_type(py_type: Any) -> dict[str, Any]:
    """Return a compact JSON Schema fragment for a Python type annotation."""
    if py_type is Any:
        return {}

    origin = get_origin(py_type)
    args = get_args(py_type)

    if origin in (UnionType, Union) or isinstance(py_type, UnionType):
        non_none = [arg for arg in args if arg is not NoneType]
        if len(non_none) == 1:
            schema = _schema_for_type(non_none[0])
            if len(non_none) != len(args):
                schema = dict(schema)
                schema["nullable"] = True
            return schema
        return {}

    if origin in (list, tuple, set, frozenset):
        item_schema = _schema_for_type(args[0]) if args else {}
        return {"type": "array", "items": item_schema}

    if origin is dict:
        return {"type": "object"}

    type_map: dict[Any, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    json_type = type_map.get(py_type)
    if json_type:
        return {"type": json_type}
    return {"type": "string"}


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


# ---------------------------------------------------------------------------
# Bundled deterministic MagLab tools
# ---------------------------------------------------------------------------


def _safe_workspace_path(path: str) -> tuple[Path, Path]:
    """Resolve a user path inside the active workspace.

    Returns ``(root, resolved_path)`` and raises ``ValueError`` when the target
    escapes the workspace. Tool calls should never read or write arbitrary
    absolute paths unless the user explicitly uses a CLI command outside the
    model tool loop.
    """
    from maglab.workspace import workspace_root

    root = workspace_root()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes active workspace: {path}") from exc
    return root, resolved


def _is_ignored_workspace_path(path: Path, root: Path) -> bool:
    """Return True when a workspace path is intentionally hidden from LLM tools."""
    from maglab.workspace import _IGNORED_NAMES

    rel = path.relative_to(root)
    return any(part in _IGNORED_NAMES for part in rel.parts)


@tool(
    read_only=True,
    description="Summarize the active MagLab workspace before project-specific work.",
)
def workspace_context(max_entries: int = 60, max_maglab_chars: int = 2_000) -> dict[str, Any]:
    """Summarize the active MagLab workspace before project-specific work."""
    from maglab.workspace import workspace_context as _workspace_context

    context = _workspace_context(max_entries=max_entries, max_maglab_chars=max_maglab_chars)
    data = context.to_dict()
    data["ok"] = True
    data["prompt"] = context.to_prompt()
    return data


@tool(
    read_only=True,
    description="List visible files in the active MagLab workspace.",
)
def workspace_tree(max_entries: int = 80) -> dict[str, Any]:
    """List visible files in the active MagLab workspace."""
    from maglab.workspace import iter_workspace_entries, workspace_root

    root = workspace_root()
    return {
        "ok": True,
        "root": str(root),
        "entries": iter_workspace_entries(root, max_entries=max_entries),
    }


@tool(
    read_only=True,
    description="Read a UTF-8 text file from the active MagLab workspace.",
)
def workspace_read_file(path: str, max_chars: int = 20_000) -> dict[str, Any]:
    """Read a UTF-8 text file from the active MagLab workspace."""
    try:
        root, target = _safe_workspace_path(path)
    except ValueError as exc:
        return {"ok": False, "path": path, "error": str(exc)}
    if _is_ignored_workspace_path(target, root):
        return {"ok": False, "path": path, "error": "Path is ignored by MagLab workspace policy."}
    if not target.exists():
        return {"ok": False, "path": path, "error": "File not found."}
    if not target.is_file():
        return {"ok": False, "path": path, "error": "Path is not a file."}
    text = target.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {
        "ok": True,
        "path": target.relative_to(root).as_posix(),
        "content": text,
        "truncated": truncated,
        "chars": len(text),
    }


@tool(
    read_only=True,
    description="Regex-search text files in the active MagLab workspace.",
)
def workspace_search(
    pattern: str,
    glob: str = "*",
    max_matches: int = 50,
    max_file_chars: int = 200_000,
) -> dict[str, Any]:
    """Regex-search text files in the active MagLab workspace."""
    from maglab.workspace import workspace_root

    root = workspace_root()
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return {"ok": False, "pattern": pattern, "error": f"Invalid regex: {exc}"}

    matches: list[dict[str, Any]] = []
    for target in sorted(root.rglob(glob), key=lambda p: p.relative_to(root).as_posix()):
        if len(matches) >= max_matches:
            break
        if not target.is_file() or _is_ignored_workspace_path(target, root):
            continue
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if len(text) > max_file_chars:
            text = text[:max_file_chars]
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(
                    {
                        "path": target.relative_to(root).as_posix(),
                        "line": lineno,
                        "text": line[:500],
                    }
                )
                if len(matches) >= max_matches:
                    break

    return {
        "ok": True,
        "root": str(root),
        "pattern": pattern,
        "glob": glob,
        "matches": matches,
        "truncated": len(matches) >= max_matches,
    }


@tool(read_only=True, description="Compute a deterministic magnetic physics formula.")
def physics_compute(formula: str, params: dict[str, float]) -> dict[str, Any]:
    """Compute a deterministic magnetic physics formula."""
    from maglab.physics import formulas as _f

    fn = getattr(_f, formula, None)
    if fn is None:
        available = [n for n in dir(_f) if not n.startswith("_") and callable(getattr(_f, n))]
        return {
            "ok": False,
            "formula": formula,
            "error": f"Unknown formula: {formula}",
            "available": available[:30],
        }
    try:
        result = fn(**params)
    except Exception as exc:
        return {"ok": False, "formula": formula, "params": params, "error": str(exc)}
    if hasattr(result, "model_dump"):
        value: Any = result.model_dump()
    elif hasattr(result, "value"):
        value = {"value": result.value, "units": getattr(result, "units", "")}
    else:
        value = result
    return {"ok": True, "formula": formula, "params": params, "result": value}


@tool(read_only=True, description="Check physical parameters with the deterministic oracle.")
def physics_check(params: dict[str, float]) -> dict[str, Any]:
    """Check physical parameters with the deterministic oracle."""
    from maglab.physics.oracle import check

    result = check(params)
    return {
        "ok": result.ok,
        "reason": result.reason,
        "param": result.param,
        "value": result.value,
        "checks": list(result.checks),
    }


@tool(read_only=True, description="Convert a magnetic quantity between supported units.")
def convert_units(value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
    """Convert a magnetic quantity between supported units."""
    from maglab.physics import units as _u

    fn_name = f"{from_unit}_to_{to_unit}"
    fn = getattr(_u, fn_name, None)
    if fn is None:
        available = [n for n in dir(_u) if "_to_" in n and not n.startswith("_")]
        return {
            "ok": False,
            "error": f"Conversion function not found: {fn_name}",
            "available": available[:30],
        }
    try:
        result = fn(value)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "input": value, "from": from_unit, "to": to_unit, "result": result}


@tool(read_only=True, description="Look up a magnetic material by MagLab material ID.")
def material_lookup(material_id: str) -> dict[str, Any] | None:
    """Look up a magnetic material by MagLab material ID."""
    from maglab.physics.materials import lookup

    mat = lookup(material_id)
    return mat.model_dump() if mat is not None else None


@tool(read_only=True, description="Search the bundled magnetic material database.")
def material_search(query: str) -> list[dict[str, Any]]:
    """Search the bundled magnetic material database."""
    from maglab.physics.materials import search

    return [m.model_dump() for m in search(query)]


@tool(read_only=True, description="Statically validate a MagLab MultiScaleSpec dictionary.")
def sim_validate(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Statically validate a MagLab MultiScaleSpec dictionary."""
    from maglab.sim.spec import MultiScaleSpec
    from maglab.sim.validate import ValidationError, validate

    try:
        spec = MultiScaleSpec.model_validate(spec_dict)
    except Exception as exc:
        return {"ok": False, "violations": None, "error": f"spec parse error: {exc}"}
    try:
        validate(spec)
        return {"ok": True, "violations": [], "error": None}
    except ValidationError as exc:
        return {
            "ok": False,
            "violations": [
                {
                    "rule": v.rule,
                    "message": v.message,
                    "actual": v.actual,
                    "recommended": v.recommended,
                    "scale_label": v.scale_label,
                }
                for v in exc.violations
            ],
            "error": str(exc),
        }


@tool(
    read_only=True,
    description="Diagnose MagLab simulation backend readiness for CPU, local GPU, SSH GPU, or SSH HPC.",
)
def sim_doctor(
    backend: str = "auto",
    host: str | None = None,
    user: str | None = None,
    probe_ssh: bool = False,
) -> dict[str, Any]:
    """Diagnose MagLab simulation backend readiness."""
    from maglab.sim.environment import diagnose_sim_environment

    return diagnose_sim_environment(
        backend=backend,
        host=host,
        user=user,
        probe_ssh=probe_ssh,
    )


@tool(
    read_only=True,
    description="Check MagLab first-run readiness for the active workspace, LLM backend, installed extras, and simulation environment.",
)
def maglab_doctor(
    feature: str = "all",
    include_sim: bool = True,
    sim_backend: str = "auto",
) -> dict[str, Any]:
    """Check MagLab first-run readiness without exposing secrets."""
    from maglab.doctor import run_doctor

    return run_doctor(
        feature=feature,
        include_sim=include_sim,
        sim_backend=sim_backend,
        probe_ssh=False,
    )


@tool(
    read_only=False,
    destructive=False,
    description="Render a MagLab FigureSpec dictionary to a PDF/SVG/EPS file in the workspace.",
)
def figure_render(
    spec_dict: dict[str, Any],
    output_path: str,
    fmt: str = "pdf",
    datapoints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render a MagLab FigureSpec dictionary to a PDF/SVG/EPS file in the workspace."""
    from maglab.figure.compose import FigureComposer
    from maglab.figure.export import FigureExporter
    from maglab.figure.spec import FigureSpec
    from maglab.provenance.datapoint import DataPoint

    try:
        root, target = _safe_workspace_path(output_path)
    except ValueError as exc:
        return {"ok": False, "path": output_path, "error": str(exc)}
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        spec = FigureSpec.model_validate(spec_dict)
    except Exception as exc:
        return {"ok": False, "path": output_path, "error": f"FigureSpec parse error: {exc}"}

    ledger: dict[str, DataPoint] = {}
    if datapoints:
        for dp_id, dp_dict in datapoints.items():
            try:
                ledger[dp_id] = DataPoint.model_validate(dp_dict)
            except Exception:
                continue

    try:
        fig = FigureComposer().compose(spec, ledger)
        saved = FigureExporter().export(fig, str(target), fmt=fmt)  # type: ignore[arg-type]
    except Exception as exc:
        return {"ok": False, "path": output_path, "error": str(exc)}
    finally:
        try:
            import matplotlib.pyplot as plt

            plt.close("all")
        except Exception:
            pass

    return {"ok": True, "path": Path(saved).relative_to(root).as_posix(), "error": None}
