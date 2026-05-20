"""Tool call abstraction — schema definition, call request and result types (provider-neutral).

§5.16, §5.18: @tool decorator, tool registry, readOnlyHint · destructiveHint.

This module defines the schemas for tools the LLM can request, and represents
tool call requests and results as provider-neutral types.
"""

from __future__ import annotations

import functools
import inspect
import json
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
    from maglab.workspace import _is_ignored_relative_path

    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return True
    return _is_ignored_relative_path(rel.as_posix())


@tool(
    read_only=True,
    description="Summarize the active MagLab workspace before project-specific work.",
)
def workspace_context(
    max_entries: int = 60,
    max_maglab_chars: int = 2_000,
    max_depth: int | None = None,
    entry_type: str = "all",
) -> dict[str, Any]:
    """Summarize the active MagLab workspace before project-specific work."""
    from maglab.workspace import workspace_context as _workspace_context

    context = _workspace_context(
        max_entries=max_entries,
        max_maglab_chars=max_maglab_chars,
        max_depth=max_depth,
        entry_type=entry_type,
    )
    data = context.to_dict()
    data["ok"] = True
    data["entry_type"] = entry_type
    data["max_depth"] = max_depth
    data["prompt"] = context.to_prompt()
    return data


@tool(
    read_only=True,
    description="List visible files in the active MagLab workspace.",
)
def workspace_tree(
    max_entries: int = 80,
    max_depth: int | None = None,
    entry_type: str = "all",
) -> dict[str, Any]:
    """List visible files in the active MagLab workspace."""
    from maglab.workspace import iter_workspace_entries, workspace_root

    root = workspace_root()
    return {
        "ok": True,
        "root": str(root),
        "entry_type": entry_type,
        "max_depth": max_depth,
        "entries": iter_workspace_entries(
            root,
            max_entries=max_entries,
            max_depth=max_depth,
            entry_type=entry_type,
        ),
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


@tool(
    read_only=True,
    description="Build an offline magnetic layer stack from bundled/literature material data.",
)
def material_build(stack: str) -> dict[str, Any]:
    """Build an offline magnetic layer stack from bundled/literature material data."""
    from maglab.physics.material_builder import build_material_stack

    try:
        result = build_material_stack(stack, use_mp=False, use_optimade=False)
    except Exception as exc:
        return {"ok": False, "stack": stack, "error": str(exc)}
    return {"ok": True, **result.model_dump(mode="json")}


@tool(read_only=True, description="List deterministic effect-fitting models available in MagLab.")
def list_effects() -> dict[str, Any]:
    """List deterministic effect-fitting models available in MagLab."""
    from maglab.analysis.providers import get_all_effects

    effects = []
    for name, model in sorted(get_all_effects().items()):
        effects.append(
            {
                "name": name,
                "subfield": model.subfield,
                "parameters": [param.name for param in model.parameters],
                "required_columns": list(model.measurement_config.required_columns),
                "geometry": model.measurement_config.geometry,
            }
        )
    return {"ok": True, "effects": effects}


@tool(
    read_only=True,
    description="Fit a deterministic MagLab effect model to a CSV file inside the active workspace.",
)
def fit_effect(
    effect: str,
    data_path: str,
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fit a deterministic MagLab effect model to a CSV file inside the active workspace."""
    try:
        root, target = _safe_workspace_path(data_path)
    except ValueError as exc:
        return {"ok": False, "effect": effect, "path": data_path, "error": str(exc)}
    if not target.is_file():
        return {"ok": False, "effect": effect, "path": data_path, "error": "File not found."}

    try:
        import pandas as pd  # type: ignore[import-untyped]

        from maglab.analysis.providers import get_effect
    except ImportError as exc:
        return {"ok": False, "effect": effect, "path": data_path, "error": str(exc)}

    try:
        model = get_effect(effect)
    except KeyError as exc:
        return {"ok": False, "effect": effect, "path": data_path, "error": str(exc)}

    try:
        df = pd.read_csv(target)
    except Exception as exc:
        return {"ok": False, "effect": effect, "path": data_path, "error": str(exc)}

    missing = [col for col in model.measurement_config.required_columns if col not in df.columns]
    if missing:
        return {
            "ok": False,
            "effect": effect,
            "path": target.relative_to(root).as_posix(),
            "missing_columns": missing,
            "columns": list(df.columns),
            "error": "Missing required columns.",
        }

    try:
        data = {col: df[col].to_numpy(dtype=float) for col in df.columns}
        result = model.fit(data, geometry=geometry)
    except Exception as exc:
        return {"ok": False, "effect": effect, "path": data_path, "error": str(exc)}

    return {
        "ok": bool(result.success),
        "effect": effect,
        "path": target.relative_to(root).as_posix(),
        "params": dict(result.params),
        "uncertainties": dict(result.uncertainties),
        "chi2": result.chi2,
        "reduced_chi2": result.reduced_chi2,
        "provenance_id": result.provenance_id,
        "message": result.message,
    }


def _fit_result_from_mapping(data: dict[str, Any]) -> Any:
    """Build a FitResult from an LLM/tool-friendly mapping."""
    import numpy as np

    from maglab.analysis.effects.base import FitResult

    return FitResult(
        params={str(k): float(v) for k, v in dict(data.get("params", {})).items()},
        uncertainties={str(k): float(v) for k, v in dict(data.get("uncertainties", {})).items()},
        chi2=float(data.get("chi2", 0.0)),
        reduced_chi2=float(data.get("reduced_chi2", 0.0)),
        covariance=np.array(data.get("covariance", []), dtype=float),
        provenance_id=str(data.get("provenance_id", "")),
        message=str(data.get("message", "")),
        success=bool(data.get("success", True)),
        effect_name=str(data.get("effect_name", data.get("effect", ""))),
    )


@tool(
    read_only=True,
    description="Return symmetry-allowed tensor components for a magnetic point group.",
)
def symmetry_allowed(point_group: str) -> dict[str, Any]:
    """Return symmetry-allowed tensor components for a magnetic point group."""
    from dataclasses import asdict

    from maglab.analysis.symmetry import allowed_components

    try:
        comp = allowed_components(point_group)
    except Exception as exc:
        return {"ok": False, "point_group": point_group, "error": str(exc)}
    return {"ok": True, **asdict(comp)}


@tool(
    read_only=True,
    description=(
        "Run deterministic physical consistency checks between fitted effects or Hall carrier-density estimates."
    ),
)
def analysis_consistency(
    result_a: dict[str, Any] | None = None,
    result_b: dict[str, Any] | None = None,
    carrier: dict[str, float] | None = None,
    checks: list[str] | None = None,
) -> dict[str, Any]:
    """Run deterministic physical consistency checks."""
    from dataclasses import asdict

    from maglab.analysis.consistency import (
        check_carrier_density_consistency,
        check_consistency,
    )

    try:
        if carrier is not None:
            result = check_carrier_density_consistency(
                r_0=float(carrier["r_0"]),
                r_0_unc=float(carrier.get("r_0_unc", 0.0)),
                n_hall=float(carrier["n_hall"]),
                n_hall_unc=float(carrier.get("n_hall_unc", 0.0)),
                rtol=float(carrier.get("rtol", 0.20)),
            )
            return {"ok": result.ok, **asdict(result)}
        if result_a is None or result_b is None:
            return {
                "ok": False,
                "error": "Provide either carrier={r_0,n_hall,...} or result_a/result_b.",
            }
        result = check_consistency(
            _fit_result_from_mapping(result_a),
            _fit_result_from_mapping(result_b),
            checks=checks,
        )
        return {"ok": result.ok, **asdict(result)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@tool(read_only=True, description="Validate and normalize a MagLab MultiScaleSpec dictionary.")
def sim_design(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a MagLab MultiScaleSpec dictionary."""
    from maglab.sim.spec import MultiScaleSpec
    from maglab.sim.validate import ValidationError, validate

    try:
        spec = MultiScaleSpec.model_validate(spec_dict)
    except Exception as exc:
        return {"ok": False, "error": f"spec parse error: {exc}", "spec": None}
    try:
        validate(spec)
        violations: list[dict[str, Any]] = []
    except ValidationError as exc:
        violations = [
            {
                "rule": v.rule,
                "message": v.message,
                "actual": v.actual,
                "recommended": v.recommended,
                "scale_label": v.scale_label,
            }
            for v in exc.violations
        ]
    return {
        "ok": not violations,
        "spec": spec.model_dump(mode="json"),
        "scale_count": len(spec.scales),
        "is_single_scale": spec.is_single_scale(),
        "violations": violations,
    }


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
    description="Parse a workspace simulation output file into a structured JobResult summary.",
)
def sim_parse(engine: str, output_path: str, job_id: str = "") -> dict[str, Any]:
    """Parse a simulation output file inside the active workspace."""
    try:
        root, target = _safe_workspace_path(output_path)
    except ValueError as exc:
        return {"ok": False, "path": output_path, "error": str(exc)}
    if _is_ignored_workspace_path(target, root):
        return {"ok": False, "path": output_path, "error": "Path is ignored by MagLab policy."}
    if not target.is_file():
        return {"ok": False, "path": output_path, "error": "File not found."}

    normalized = engine.strip().lower()
    try:
        if normalized == "mumax3":
            from maglab.sim.parse import parse_mumax3_table

            result = parse_mumax3_table(target, job_id=job_id)
        elif normalized == "oommf":
            from maglab.sim.parse import parse_oommf_odt

            result = parse_oommf_odt(target, job_id=job_id)
        elif normalized in {"magnumnp", "magnum.np", "magnum_np"}:
            from maglab.sim.parse import parse_magnumnp_result

            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {
                    "ok": False,
                    "path": target.relative_to(root).as_posix(),
                    "error": "magnumnp parse expects a JSON object file.",
                }
            result = parse_magnumnp_result(
                data, job_id=job_id or target.stem, source_ref=str(target)
            )
        else:
            return {
                "ok": False,
                "path": target.relative_to(root).as_posix(),
                "error": "Unsupported engine. Use mumax3, oommf, or magnumnp.",
            }
    except Exception as exc:
        return {"ok": False, "path": target.relative_to(root).as_posix(), "error": str(exc)}
    return {
        "ok": True,
        "path": target.relative_to(root).as_posix(),
        "summary": result.summary(),
        "result": result.model_dump(mode="json"),
    }


@tool(
    read_only=False,
    destructive=False,
    description=(
        "Run the deterministic MagLab simulation pipeline in workspace scope. "
        "Defaults to mock mode; real solver backends require allow_real=True."
    ),
)
def sim_run(
    backend: str = "mock",
    scales: list[str] | None = None,
    work_dir: str = "maglab_sim/pipeline",
    target_temp_k: float = 300.0,
    allow_real: bool = False,
) -> dict[str, Any]:
    """Run the multiscale simulation pipeline with safe defaults."""
    normalized_backend = backend.strip().lower().replace("-", "_")
    if normalized_backend != "mock" and not allow_real:
        return {
            "ok": False,
            "backend": backend,
            "error": "Non-mock simulation backends require allow_real=True and explicit user approval.",
        }
    try:
        root, target = _safe_workspace_path(work_dir)
    except ValueError as exc:
        return {"ok": False, "backend": backend, "error": str(exc)}
    if _is_ignored_workspace_path(target, root):
        return {"ok": False, "backend": backend, "error": "Path is ignored by MagLab policy."}
    try:
        from maglab.sim.pipeline import run_pipeline

        result = run_pipeline(
            scales=scales,
            backend=normalized_backend,
            work_dir=target,
            target_temp_K=target_temp_k,
        )
        manifest = target / "pipeline_result.json"
        manifest.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        return {"ok": False, "backend": backend, "error": str(exc)}
    return {
        "ok": not result.errors,
        "backend": normalized_backend,
        "path": target.relative_to(root).as_posix(),
        "work_dir": target.relative_to(root).as_posix(),
        "manifest": manifest.relative_to(root).as_posix(),
        "summary": result.summary(),
        "result": result.to_dict(),
        "error": "; ".join(result.errors) if result.errors else None,
    }


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


@tool(read_only=True, description="Validate and summarize a MagLab FigureSpec dictionary.")
def figure_design(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Validate and summarize a MagLab FigureSpec before rendering."""
    from maglab.figure.spec import FigureSpec

    try:
        spec = FigureSpec.model_validate(spec_dict)
    except Exception as exc:
        return {"ok": False, "error": f"FigureSpec parse error: {exc}", "spec": None}
    return {
        "ok": True,
        "figure_id": spec.figure_id,
        "journal": str(spec.journal),
        "column_width": str(spec.column_width),
        "layout": spec.layout.model_dump(mode="json"),
        "panel_count": len(spec.panels),
        "panels": [
            {
                "panel_id": panel.panel_id,
                "panel_type": str(panel.panel_type),
                "plot_kind": str(panel.plot_kind) if panel.plot_kind else "",
                "data_point_ids": list(panel.data_point_ids),
                "title": panel.title,
            }
            for panel in spec.panels
        ],
        "provenance_ids": spec.all_data_point_ids(),
        "spec": spec.model_dump(mode="json"),
    }


@tool(read_only=True, description="Compose a MagLab FigureSpec in memory to check renderability.")
def figure_compose(
    spec_dict: dict[str, Any],
    datapoints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose a MagLab FigureSpec without writing files."""
    from maglab.figure.compose import FigureComposer
    from maglab.figure.spec import FigureSpec
    from maglab.provenance.datapoint import DataPoint

    try:
        spec = FigureSpec.model_validate(spec_dict)
    except Exception as exc:
        return {"ok": False, "error": f"FigureSpec parse error: {exc}"}

    ledger: dict[str, DataPoint] = {}
    if datapoints:
        for dp_id, dp_dict in datapoints.items():
            try:
                ledger[dp_id] = DataPoint.model_validate(dp_dict)
            except Exception:
                continue

    try:
        fig = FigureComposer().compose(spec, ledger)
        axes_count = len(fig.axes)
    except Exception as exc:
        return {"ok": False, "figure_id": spec.figure_id, "error": str(exc)}
    finally:
        try:
            import matplotlib.pyplot as plt

            plt.close("all")
        except Exception:
            pass
    return {"ok": True, "figure_id": spec.figure_id, "axes_count": axes_count, "error": None}


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


@tool(
    read_only=False,
    destructive=False,
    description="Export a MagLab FigureSpec dictionary to multiple vector/raster files in the workspace.",
)
def figure_export(
    spec_dict: dict[str, Any],
    stem: str,
    formats: list[str] | None = None,
    datapoints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export a MagLab FigureSpec to multiple formats in the workspace."""
    from maglab.figure.compose import FigureComposer
    from maglab.figure.export import FigureExporter
    from maglab.figure.spec import FigureSpec
    from maglab.provenance.datapoint import DataPoint

    try:
        root, target = _safe_workspace_path(stem)
    except ValueError as exc:
        return {"ok": False, "stem": stem, "paths": {}, "error": str(exc)}
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        spec = FigureSpec.model_validate(spec_dict)
    except Exception as exc:
        return {"ok": False, "stem": stem, "paths": {}, "error": f"FigureSpec parse error: {exc}"}

    ledger: dict[str, DataPoint] = {}
    if datapoints:
        for dp_id, dp_dict in datapoints.items():
            try:
                ledger[dp_id] = DataPoint.model_validate(dp_dict)
            except Exception:
                continue

    selected_formats = formats or ["pdf", "svg"]
    try:
        fig = FigureComposer().compose(spec, ledger)
        saved = FigureExporter().export_all(
            fig,
            str(target),
            formats=selected_formats,  # type: ignore[arg-type]
            figure_id=spec.figure_id,
        )
    except Exception as exc:
        return {"ok": False, "stem": stem, "paths": {}, "error": str(exc)}
    finally:
        try:
            import matplotlib.pyplot as plt

            plt.close("all")
        except Exception:
            pass
    return {
        "ok": True,
        "stem": target.relative_to(root).as_posix(),
        "paths": {fmt: path.relative_to(root).as_posix() for fmt, path in saved.items()},
        "error": None,
    }


@tool(read_only=True, description="List or search journal-ready schematic figure primitives.")
def figure_list_primitives(query: str = "", max_results: int = 30) -> dict[str, Any]:
    """List or search journal-ready schematic figure primitives."""
    from maglab.figure.primitives.registry import make_default_registry

    registry = make_default_registry()
    entries = registry.search(query, max_results=max_results) if query else registry.list_all()
    return {
        "ok": True,
        "query": query,
        "primitives": [
            {
                "name": str(entry.get("name", "")),
                "category": str(entry.get("category", "")),
                "tags": list(entry.get("tags", [])),
                "description": str(entry.get("description", "")),
                "journal_styles": list(entry.get("journal_styles", [])),
            }
            for entry in entries[:max_results]
        ],
    }


@tool(read_only=True, description="Show metadata for one journal-ready schematic figure primitive.")
def figure_show_primitive(name: str) -> dict[str, Any]:
    """Show metadata for one journal-ready schematic figure primitive."""
    from maglab.figure.primitives.registry import make_default_registry

    registry = make_default_registry()
    index = {str(entry.get("name", "")): entry for entry in registry.list_all()}
    entry = index.get(name)
    if entry is None:
        return {
            "ok": False,
            "name": name,
            "available": sorted(index),
            "error": "Primitive not found.",
        }
    return {
        "ok": True,
        "name": name,
        "category": str(entry.get("category", "")),
        "tags": list(entry.get("tags", [])),
        "description": str(entry.get("description", "")),
        "journal_styles": list(entry.get("journal_styles", [])),
    }


@tool(
    read_only=True,
    network=True,
    description="Search scholarly literature by query using a selected MagLab connector.",
)
def literature_search(
    query: str,
    max_results: int = 10,
    source: str = "openalex",
) -> dict[str, Any]:
    """Search scholarly literature by query."""
    normalized = source.strip().lower().replace("-", "_")
    try:
        connector: Any
        if normalized == "openalex":
            from maglab.literature.connectors import OpenAlexConnector

            connector = OpenAlexConnector()
        elif normalized in {"semantic_scholar", "s2", "semanticscholar"}:
            from maglab.literature.connectors import SemanticScholarConnector

            connector = SemanticScholarConnector()
        elif normalized == "arxiv":
            from maglab.literature.connectors import ArXivConnector

            connector = ArXivConnector()
        else:
            return {
                "ok": False,
                "query": query,
                "source": source,
                "records": [],
                "error": "Unsupported source. Use openalex, semantic_scholar, or arxiv.",
            }
        records = connector.search(query, max_results=max_results)
    except Exception as exc:
        return {"ok": False, "query": query, "source": source, "records": [], "error": str(exc)}
    return {
        "ok": True,
        "query": query,
        "source": normalized,
        "records": [record.model_dump(mode="json") for record in records],
        "count": len(records),
    }


@tool(
    read_only=True,
    network=True,
    description="Find authoritative authors for a research topic using OpenAlex/Semantic Scholar enrichment.",
)
def literature_find_authors(
    topic: str,
    max_results: int = 10,
    email: str = "",
    enrich_s2: bool = True,
) -> dict[str, Any]:
    """Find authoritative authors for a topic."""
    try:
        from maglab.literature.authors import find_authoritative_authors

        authors = find_authoritative_authors(
            topic,
            max_results=max_results,
            email=email,
            enrich_s2=enrich_s2,
        )
    except Exception as exc:
        return {"ok": False, "topic": topic, "authors": [], "error": str(exc)}
    return {
        "ok": True,
        "topic": topic,
        "authors": [author.model_dump(mode="json") for author in authors],
        "count": len(authors),
    }


@tool(
    read_only=True, description="Extract weighted research keywords from text or workspace files."
)
def literature_keywords(
    texts: list[str] | None = None,
    folder: str | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """Extract weighted research keywords from text or a workspace folder."""
    try:
        if folder:
            root, target = _safe_workspace_path(folder)
            if _is_ignored_workspace_path(target, root):
                return {"ok": False, "keywords": [], "error": "Path is ignored by MagLab policy."}
            if not target.is_dir():
                return {"ok": False, "keywords": [], "error": "Folder not found."}
            from maglab.literature.keywords import extract_keywords_from_folder

            keywords = extract_keywords_from_folder(target, top_n=top_n)
        else:
            from maglab.literature.keywords import extract_keywords_from_texts

            keywords = extract_keywords_from_texts(texts or [], top_n=top_n)
    except Exception as exc:
        return {"ok": False, "keywords": [], "error": str(exc)}
    return {
        "ok": True,
        "keywords": [keyword.model_dump(mode="json") for keyword in keywords],
        "count": len(keywords),
        "error": None,
    }


@tool(
    read_only=True,
    network=True,
    description="Retrieve journal metrics with explicit SJR/OpenAlex/Eigenfactor source labels.",
)
def journal_metrics(journal_name: str, use_openalex: bool = False) -> dict[str, Any]:
    """Retrieve journal metrics without using forbidden JCR impact-factor labels."""
    try:
        from maglab.literature.journals import get_journal_metrics

        metrics = get_journal_metrics(journal_name, use_openalex=use_openalex)
    except Exception as exc:
        return {"ok": False, "journal_name": journal_name, "error": str(exc)}
    return {"ok": True, **metrics.model_dump(mode="json"), "error": None}


def _safety_violation_to_dict(violation: Any) -> dict[str, Any]:
    """Serialize a SafetyViolation with enum values normalized."""
    return {
        "violation_type": str(getattr(violation.violation_type, "value", violation.violation_type)),
        "line_number": violation.line_number,
        "command": violation.command,
        "message": violation.message,
        "is_error": violation.is_error,
    }


@tool(
    read_only=True,
    description="Run the deterministic SCPI safety-envelope validator on commands or script text.",
)
def instr_safety_check(
    model: str = "generic",
    commands: list[str] | None = None,
    script_text: str | None = None,
) -> dict[str, Any]:
    """Run static SCPI safety validation without touching hardware."""
    try:
        from maglab.instrument.safety import check_scpi, check_script

        result = (
            check_script(script_text, model=model)
            if script_text is not None
            else check_scpi(commands or [], model=model)
        )
    except Exception as exc:
        return {"ok": False, "profile": model, "violations": [], "warnings": [], "error": str(exc)}
    return {
        "ok": result.ok,
        "profile": result.profile_used,
        "violations": [_safety_violation_to_dict(v) for v in result.violations],
        "warnings": [_safety_violation_to_dict(v) for v in result.warnings],
        "summary": result.summary(),
        "error": None,
    }


@tool(
    read_only=True,
    description="Query workspace provenance artifacts and optionally summarize a W3C PROV SQLite store.",
)
def provenance_query(db_path: str = "", max_entries: int = 50) -> dict[str, Any]:
    """Query existing provenance artifacts in the active workspace."""
    from dataclasses import asdict

    from maglab.project_status import discover_provenance_artifacts, summarize_provenance_db
    from maglab.workspace import workspace_root

    root = workspace_root()
    artifacts = discover_provenance_artifacts(root, max_entries=max_entries)
    db_summary: dict[str, Any] | None = None
    if db_path:
        try:
            safe_root, target = _safe_workspace_path(db_path)
        except ValueError as exc:
            return {"ok": False, "artifacts": [], "db": None, "error": str(exc)}
        if _is_ignored_workspace_path(target, safe_root):
            return {"ok": False, "artifacts": [], "db": None, "error": "Path is ignored."}
        db_summary = summarize_provenance_db(target)
    return {
        "ok": True,
        "root": str(root),
        "artifacts": [asdict(artifact) for artifact in artifacts],
        "db": db_summary,
        "error": None,
    }


@tool(
    read_only=False,
    destructive=False,
    network=True,
    description="Search and cache an instrument manual PDF for a user-confirmed model name.",
)
def instr_search_manual(model: str, manufacturer: str | None = None) -> dict[str, Any]:
    """Search and download an instrument manual PDF."""
    try:
        from maglab.instrument.manual_search import ManualSearcher

        result = ManualSearcher().search_and_download(model, manufacturer=manufacturer)
    except Exception as exc:
        return {"ok": False, "pdf_path": None, "url": None, "cached": False, "error": str(exc)}
    return {
        "ok": result.ok,
        "pdf_path": str(result.pdf_path) if result.pdf_path else None,
        "url": result.url,
        "cached": result.cached,
        "sha256": result.sha256,
        "error": result.error,
    }


@tool(
    read_only=False,
    destructive=False,
    description="Ingest a workspace instrument manual PDF into the SCPI RAG index.",
)
def instr_ingest_manual(
    model: str,
    pdf_path: str,
    manufacturer: str | None = None,
) -> dict[str, Any]:
    """Ingest a local manual PDF into the instrument RAG index."""
    try:
        _root, target = _safe_workspace_path(pdf_path)
    except ValueError as exc:
        return {"ok": False, "chunk_count": 0, "model_key": "", "error": str(exc)}
    if not target.is_file():
        return {"ok": False, "chunk_count": 0, "model_key": "", "error": "File not found."}
    try:
        from maglab.instrument.manual_rag import ManualRAGPipeline
        from maglab.instrument.manual_search import ManualSearcher

        cache_result = ManualSearcher().ingest_local(model, target, manufacturer=manufacturer)
        index = ManualRAGPipeline().ingest(model_key=model, pdf_path=target)
    except Exception as exc:
        return {"ok": False, "chunk_count": 0, "model_key": "", "error": str(exc)}
    return {
        "ok": True,
        "chunk_count": index.chunk_count,
        "model_key": model,
        "cached_at": str(cache_result.pdf_path) if cache_result.pdf_path else None,
        "error": None,
    }


@tool(
    read_only=False,
    destructive=False,
    description="Generate a workspace-local instrument SKILL.md package from an ingested manual index.",
)
def instr_generate_skill(
    model: str,
    manufacturer: str,
    safety_model: str = "generic",
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Generate an instrument skill package."""
    try:
        output_root = None
        if output_dir:
            root, target = _safe_workspace_path(output_dir)
            if _is_ignored_workspace_path(target, root):
                return {"ok": False, "skill_dir": "", "files": [], "error": "Path is ignored."}
            output_root = target
        from maglab.instrument.skillgen import SkillGenerator

        pkg = SkillGenerator(output_root=output_root).generate(
            model=model,
            manufacturer=manufacturer,
            safety_model=safety_model,
        )
    except Exception as exc:
        return {"ok": False, "skill_dir": "", "files": [], "error": str(exc)}
    return {
        "ok": pkg.ok,
        "skill_dir": str(pkg.skill_dir),
        "files": [str(path) for path in pkg.files],
        "chunk_count": pkg.chunk_count,
        "error": None if pkg.ok else "SKILL.md was not generated",
    }


@tool(
    read_only=False,
    destructive=False,
    description="Generate a PyVISA backend skeleton for a user-confirmed instrument model.",
)
def instr_scaffold(
    model: str,
    iface: str = "GPIB",
    output_path: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a PyVISA backend skeleton without touching hardware."""
    try:
        out = None
        root = None
        if output_path:
            root, out = _safe_workspace_path(output_path)
            if _is_ignored_workspace_path(out, root):
                return {"ok": False, "code": "", "output_path": None, "error": "Path is ignored."}
            out.parent.mkdir(parents=True, exist_ok=True)
        from maglab.instrument.scaffold import generate_scaffold

        code = generate_scaffold(model=model, iface=iface, output_path=out, options=options)
    except Exception as exc:
        return {"ok": False, "code": "", "output_path": None, "error": str(exc)}
    return {
        "ok": True,
        "code": code,
        "output_path": out.relative_to(root).as_posix() if out is not None and root else None,
        "error": None,
    }


@tool(read_only=True, description="Build a deterministic reviewer panel specification.")
def reviewer_build_panel(
    journal: str = "general",
    personas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a reviewer panel spec without invoking an LLM."""
    from dataclasses import asdict

    from maglab.reviewer.rubrics import get_rubric

    default_personas = personas or [
        {"author_id": "reviewer_a", "author_name": "Methods reviewer", "paper_count": 0},
        {"author_id": "reviewer_b", "author_name": "Physics reviewer", "paper_count": 0},
        {"author_id": "reviewer_c", "author_name": "Figures reviewer", "paper_count": 0},
    ]
    rubric = get_rubric(journal)
    return {
        "ok": True,
        "journal": rubric.journal,
        "personas": default_personas,
        "rubric": asdict(rubric),
    }


@tool(read_only=True, description="Run the deterministic reviewer panel in no-LLM dummy mode.")
def reviewer_run_review(
    manuscript: str,
    journal: str = "general",
    personas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a reviewer panel without network calls or fabricated citations."""
    try:
        from maglab.reviewer.corpus_rag import CorpusRAG
        from maglab.reviewer.panel import PersonaSpec, ReviewPanel

        specs = [
            PersonaSpec(
                author_id=str(item.get("author_id", f"reviewer_{idx}")),
                author_name=str(item.get("author_name", f"Reviewer {idx}")),
                paper_count=int(item.get("paper_count", 0)),
            )
            for idx, item in enumerate(personas or [], start=1)
        ]
        if not specs:
            specs = [
                PersonaSpec("reviewer_a", "Methods reviewer", 0),
                PersonaSpec("reviewer_b", "Physics reviewer", 0),
                PersonaSpec("reviewer_c", "Figures reviewer", 0),
            ]
        panel = ReviewPanel(specs, CorpusRAG(), journal=journal, llm_review_fn=None)
        result = panel.review(manuscript, raise_on_disclosure_violation=False)
    except Exception as exc:
        return {"ok": False, "journal": journal, "reviews": [], "error": str(exc)}
    return {
        "ok": True,
        "journal": result.journal,
        "reviews": [
            {
                "persona": review.persona.author_name or review.persona.author_id,
                "recommendation": review.score.summary_recommendation,
                "validation_errors": list(review.validation_errors),
                "disclosure_passed": review.disclosure_passed,
                "review_text": review.review_text,
            }
            for review in result.reviews
        ],
        "error": None,
    }


@tool(read_only=True, description="Draft a guarded manuscript section scaffold.")
def authoring_draft_section(
    section: str,
    context: str,
    verified_cite_keys: list[str] | None = None,
    datapoints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Draft a section scaffold using the authoring DataVault guardrails."""
    try:
        from maglab.authoring.bib_manager import BibManager
        from maglab.authoring.citation_auditor import VerifiedCitePool
        from maglab.authoring.data_vault import DataVault
        from maglab.authoring.section_drafter import SectionDrafter
        from maglab.provenance.datapoint import DataPoint

        vault = DataVault(
            {
                key: DataPoint.model_validate(value)
                for key, value in dict(datapoints or {}).items()
                if isinstance(value, dict)
            }
        )
        pool = VerifiedCitePool(cite_keys=list(verified_cite_keys or []))

        def _stub_llm(_system: str, _user: str) -> str:
            return context or "[FILL: author-provided section context]"

        result = SectionDrafter(vault, BibManager(), _stub_llm).draft_section(
            section, context, pool
        )
    except Exception as exc:
        return {"ok": False, "section": section, "tex": "", "error": str(exc)}
    return {
        "ok": True,
        "section": str(result.section),
        "tex": result.tex,
        "used_cite_keys": list(result.used_cite_keys),
        "human_review_required": result.human_review_required,
        "error": None,
    }


@tool(read_only=True, description="Verify citation existence and optional semantic support.")
def authoring_verify_citations(
    draft_tex: str,
    verified_records: list[dict[str, Any]] | None = None,
    full_text_pool: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify citation keys against a deterministic verified BibTeX pool."""
    try:
        from maglab.authoring.bib_manager import BibManager
        from maglab.authoring.citation_auditor import audit_existence, audit_semantics

        manager = BibManager()
        for record in verified_records or []:
            doi = str(record.get("doi", "")).strip()
            if doi:
                manager.add_verified(doi, record)
        existence = audit_existence(draft_tex, manager, raise_on_missing=False)
        semantics = audit_semantics(
            draft_tex,
            manager,
            full_text_pool=full_text_pool or {},
            raise_on_blocking=False,
        )
    except Exception as exc:
        return {"ok": False, "missing_keys": [], "semantic_blocking": [], "error": str(exc)}
    return {
        "ok": existence.all_present and semantics.passes_gate,
        "missing_keys": list(existence.missing_keys),
        "semantic_blocking": [
            {
                "cite_key": finding.cite_key,
                "claim_sentence": finding.claim_sentence,
                "label": str(finding.label),
                "confidence": finding.confidence,
            }
            for finding in semantics.blocking_findings
        ],
        "error": None,
    }


@tool(read_only=True, description="Draft a human-review-required academic communication.")
def comms_draft(kind: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Draft academic communications with HUMAN REVIEW REQUIRED guardrails."""
    try:
        from maglab.authoring.comms.academic_email import AcademicEmailAgent
        from maglab.authoring.comms.conference_abstract import ConferenceAbstractAgent
        from maglab.authoring.comms.cover_letter import CoverLetterAgent
        from maglab.authoring.comms.grant_text import GrantTextAgent
        from maglab.authoring.comms.rebuttal import RebuttalAgent
        from maglab.authoring.comms.revision_letter import RevisionLetterAgent

        def _stub_llm(_system: str, user: str) -> str:
            topic = str(inputs.get("topic") or inputs.get("results_context") or user[:160])
            return (
                "Subject: [FILL: subject]\n\n"
                "[FILL: greeting]\n\n"
                f"{topic}\n\n"
                "[FILL: sender name and affiliation]"
            )

        key = kind.strip().lower().replace("_", "-")
        agent_cls: Any
        if key == "abstract":
            agent_cls = ConferenceAbstractAgent
        elif key == "cover-letter":
            agent_cls = CoverLetterAgent
        elif key == "grant":
            agent_cls = GrantTextAgent
        elif key == "rebuttal":
            agent_cls = RebuttalAgent
        elif key == "revision":
            agent_cls = RevisionLetterAgent
        else:
            agent_cls = AcademicEmailAgent
        result = agent_cls(_stub_llm).draft(inputs)
    except Exception as exc:
        return {"ok": False, "kind": kind, "text": "", "error": str(exc)}
    return {
        "ok": result.is_ready_for_review(),
        "kind": kind,
        "text": result.text,
        "fill_markers": list(result.fill_markers),
        "word_count": result.word_count,
        "error": None,
    }


@tool(
    read_only=False,
    destructive=False,
    description="Build a workspace artifact inventory report covering outputs, provenance, and task files.",
)
def report_build(output_path: str = "maglab_report/inventory.json") -> dict[str, Any]:
    """Build a deterministic workspace artifact inventory report."""
    from dataclasses import asdict

    try:
        root, target = _safe_workspace_path(output_path)
    except ValueError as exc:
        return {"ok": False, "path": output_path, "error": str(exc)}
    if _is_ignored_workspace_path(target, root):
        return {"ok": False, "path": output_path, "error": "Path is ignored by MagLab policy."}
    try:
        from maglab.project_status import (
            discover_provenance_artifacts,
            discover_report_artifacts,
            task_scaffold_inventory,
        )

        payload = {
            "workspace": str(root),
            "reports": [asdict(item) for item in discover_report_artifacts(root)],
            "provenance": [asdict(item) for item in discover_provenance_artifacts(root)],
            "tasks": [asdict(item) for item in task_scaffold_inventory(root)],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "path": output_path, "error": str(exc)}
    return {
        "ok": True,
        "path": target.relative_to(root).as_posix(),
        "counts": {key: len(value) for key, value in payload.items() if isinstance(value, list)},
        "error": None,
    }
