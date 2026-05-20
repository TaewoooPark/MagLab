"""Terminal setup registry for MagLab research features.

The registry centralizes optional dependency extras, terminal setup commands,
and slash command names. It does not install packages automatically; it gives
the exact command and then keeps feature-specific configuration inside MagLab's
terminal flow.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import platformdirs
from rich.console import Console
from rich.markup import escape
from rich.table import Table

RECOMMENDED_INSTALL = 'pipx install --python python3.12 --editable ".[research]"'
UV_TOOL_INSTALL = 'uv tool install --python python3.12 --editable ".[research]"'
PIPX_INSTALL = 'pipx install --python python3.12 --editable ".[research]"'
DEV_INSTALL = 'uv pip install -e ".[research]"'
PIP_INSTALL = 'python -m pip install -e ".[research]"'


@dataclass(frozen=True)
class FeatureSetup:
    """Setup metadata for one MagLab research feature."""

    key: str
    title: str
    extra: str
    slash: str
    imports: tuple[str, ...] = ()
    optional_imports: tuple[str, ...] = ()
    binaries: tuple[str, ...] = ()
    setup_commands: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    aliases: tuple[str, ...] = field(default_factory=tuple)


FEATURES: dict[str, FeatureSetup] = {
    "llm": FeatureSetup(
        key="llm",
        title="LLM orchestration backend",
        extra="llm",
        slash="/setup-llm",
        imports=("litellm", "ollama"),
        binaries=("codex", "ollama"),
        setup_commands=(
            "maglab auth codex",
            "maglab auth anthropic",
            "maglab auth grok",
            "maglab auth deepseek",
            "maglab auth qwen",
            "maglab auth kimi",
            "maglab auth gemini",
            "maglab auth openai",
            "maglab auth status",
            "maglab auth test",
        ),
        notes=(
            "Recommended backend is Codex delegated CLI.",
            "MagLab stores backend selection only; Codex OAuth stays in the official CLI.",
            "Direct API providers are Anthropic, Grok, DeepSeek, Qwen, Kimi, Gemini, and OpenAI.",
            "Inside REPL, use /connect codex, /connect <provider>, /connect api <provider>, or /connect ollama.",
        ),
        aliases=("backend", "codex", "api", "ollama", "provider"),
    ),
    "literature": FeatureSetup(
        key="literature",
        title="Literature intelligence",
        extra="literature",
        slash="/setup-literature",
        imports=("pyalex", "semanticscholar", "arxiv", "habanero", "sklearn", "keybert", "yake"),
        setup_commands=(
            'maglab lit search "spin orbit torque"',
            'maglab lit authors "orbital Hall effect ferromagnet"',
            "maglab lit journal prl",
        ),
        notes=(
            "OpenAlex works best when you set a contact email in your shell or config workflow.",
        ),
        aliases=("lit",),
    ),
    "simulation": FeatureSetup(
        key="simulation",
        title="Multiscale simulation",
        extra="sim",
        slash="/setup-simulation",
        imports=("discretisedfield", "micromagneticmodel", "oommfc", "magnumnp"),
        optional_imports=("paramiko",),
        binaries=("mumax3", "oommf", "nvidia-smi", "ssh", "rsync", "sbatch"),
        setup_commands=(
            "maglab sim doctor",
            "maglab sim doctor --backend ssh-gpu --host <host> --user <user>",
            "maglab sim doctor --backend ssh-hpc --host <host> --user <user> --probe-ssh",
            "maglab sim validate examples/sim/micro.yaml",
            "maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock",
        ),
        notes=(
            "Python simulation libraries install through the research extra.",
            "Paramiko is included in the sim/research extras for SSH workflows; missing Paramiko only blocks Python-native remote execution, not mock or local CPU readiness.",
            "External solvers such as MuMax3/OOMMF still need system installation when not using mock mode.",
            "Use sim doctor before real GPU or cluster time; SSH is only probed when --probe-ssh is explicit.",
        ),
        aliases=("sim",),
    ),
    "figure": FeatureSetup(
        key="figure",
        title="Figure production",
        extra="figure",
        slash="/setup-figure",
        imports=("matplotlib", "scienceplots", "pyvista", "cairosvg"),
        setup_commands=("maglab figure primitives list", "maglab figure spec"),
        notes=("Headless 3D rendering may need a working OpenGL/OSMesa environment.",),
        aliases=("fig",),
    ),
    "instrument": FeatureSetup(
        key="instrument",
        title="Instrument and manual-to-skill workflows",
        extra="instr",
        slash="/setup-instrument",
        imports=("pyvisa", "pyvisa_sim", "pdfplumber"),
        setup_commands=(
            "maglab instr scaffold lockin --interface visa",
            "maglab instr check generated_script.py",
        ),
        notes=(
            "Actual hardware execution remains a human-approved Tier 3 action.",
            "Install vendor VISA drivers separately when using real instruments.",
        ),
        aliases=("instr", "manual"),
    ),
    "authoring": FeatureSetup(
        key="authoring",
        title="Authoring and communications",
        extra="authoring",
        slash="/setup-authoring",
        imports=("bibtexparser", "pylatex", "pptx", "docx"),
        binaries=("latexmk",),
        setup_commands=(
            'maglab write "verified results summary" --journal prl --dry-run',
            "maglab comms abstract --help",
            "maglab present slides --help",
        ),
        notes=("LaTeX compilation requires a TeX distribution if you enable PDF output.",),
        aliases=("write", "comms", "present"),
    ),
    "review": FeatureSetup(
        key="review",
        title="Review and anomaly explanation",
        extra="reviewer",
        slash="/setup-review",
        imports=("rank_bm25",),
        setup_commands=("maglab review manuscript.md", "maglab explain data.csv"),
        notes=("Review outputs are advisory and require human review before use.",),
        aliases=("reviewer", "explain"),
    ),
    "gateway": FeatureSetup(
        key="gateway",
        title="Slack, Telegram, and Discord gateway",
        extra="gateway",
        slash="/setup-gateway",
        imports=("slack_bolt", "telegram", "discord"),
        setup_commands=("maglab gateway setup", "maglab gateway status"),
        notes=(
            "Platform bot tokens are configured in the terminal and stored outside source files.",
        ),
    ),
    "mcp": FeatureSetup(
        key="mcp",
        title="MCP client/server integration",
        extra="mcp",
        slash="/setup-mcp",
        imports=("fastmcp", "mcp"),
        setup_commands=("maglab mcp serve", "maglab mcp list"),
        notes=("Use trusted server allowlists before enabling remote MCP tools.",),
    ),
}

_ALIASES: dict[str, str] = {
    alias: key for key, feature in FEATURES.items() for alias in (feature.key, *feature.aliases)
}
_ALIASES["all"] = "all"
_ALIASES["research"] = "all"


def normalize_feature(name: str | None) -> str:
    """Normalize feature names and aliases."""
    if not name:
        return "all"
    key = name.strip().lower().replace("_", "-")
    return _ALIASES.get(key, key)


def list_feature_keys() -> list[str]:
    """Return canonical feature keys."""
    return sorted(FEATURES)


def _module_ok(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _binary_ok(binary: str) -> bool:
    return shutil.which(binary) is not None


def _status_line(items: Iterable[str], checker: Callable[[str], bool]) -> list[str]:
    lines: list[str] = []
    for item in items:
        ok = checker(item)
        marker = "ok" if ok else "missing"
        lines.append(f"{item}: {marker}")
    return lines


def _compact_status(items: Iterable[str], checker: Callable[[str], bool]) -> str:
    """Return a compact readiness label for setup summary tables."""
    values = list(items)
    if not values:
        return "n/a"
    missing = [item for item in values if not checker(item)]
    if not missing:
        return "ready"
    visible = ", ".join(missing[:3])
    if len(missing) > 3:
        visible += f", +{len(missing) - 3}"
    return visible


def _maglab_command_probe(maglab_cmd: str | None, expected_version: str) -> dict[str, object]:
    """Probe the PATH command without mutating installation state."""
    if maglab_cmd is None:
        return {
            "status": "needs-install",
            "maglab": None,
            "version_output": "",
            "detail": "not found on PATH",
        }
    try:
        proc = subprocess.run(
            [maglab_cmd, "version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "blocked",
            "maglab": maglab_cmd,
            "version_output": "",
            "detail": f"could not run `maglab version`: {exc}",
        }
    output = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0:
        return {
            "status": "blocked",
            "maglab": maglab_cmd,
            "version_output": output,
            "detail": f"`maglab version` exited {proc.returncode}",
        }
    status = "ready" if expected_version in output else "stale"
    detail = output if output else "no version output"
    return {
        "status": status,
        "maglab": maglab_cmd,
        "version_output": output,
        "detail": detail,
    }


def build_install_doctor_report() -> dict[str, object]:
    """Return a read-only installation preflight report."""
    from maglab import __version__
    from maglab.workspace import workspace_info

    current_python = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    python_status = (
        "ready"
        if sys.version_info[:2] == (3, 12)
        else "usable"
        if sys.version_info[:2] >= (3, 11)
        else "blocked"
    )
    maglab_cmd = shutil.which("maglab")
    command_probe = _maglab_command_probe(maglab_cmd, __version__)
    pipx_cmd = shutil.which("pipx")
    uv_cmd = shutil.which("uv")
    pip_cmd = shutil.which("pip") or shutil.which("pip3")
    workspace = workspace_info()

    feature_rows: list[dict[str, object]] = []
    for feature in FEATURES.values():
        missing_python = [name for name in feature.imports if not _module_ok(name)]
        optional_python = {name: _module_ok(name) for name in feature.optional_imports}
        missing_optional_python = [name for name, ok in optional_python.items() if not ok]
        missing_external = [name for name in feature.binaries if not _binary_ok(name)]
        feature_rows.append(
            {
                "key": feature.key,
                "extra": feature.extra,
                "slash": feature.slash,
                "python_ready": not missing_python,
                "external_ready": not missing_external,
                "optional_python_ready": not missing_optional_python,
                "optional_python": optional_python,
                "missing_python": missing_python,
                "missing_optional_python": missing_optional_python,
                "missing_external": missing_external,
                "install_command": f'pipx inject maglab "maglab[{feature.extra}]"',
                "setup_command": f"maglab setup {feature.key}",
            }
        )

    next_actions: list[str] = []
    if python_status != "ready":
        next_actions.append("Use Python 3.12 for the known-good global install path.")
    if command_probe["status"] == "needs-install":
        next_actions.append(f"Install the global command: {RECOMMENDED_INSTALL}")
    elif command_probe["status"] == "stale":
        next_actions.append(f"Refresh the global command: {RECOMMENDED_INSTALL}")
    elif command_probe["status"] == "blocked":
        next_actions.append(
            "Fix the `maglab` executable on PATH, then rerun `maglab install doctor`."
        )
    if pipx_cmd is None and uv_cmd is None:
        next_actions.append("Install pipx or uv before using the global tool install path.")
    if any(not row["python_ready"] for row in feature_rows):
        next_actions.append(f"Install all research extras at once: {RECOMMENDED_INSTALL}")
    if any(row["missing_optional_python"] for row in feature_rows):
        next_actions.append(
            "Optional Python packages are missing for advanced paths; run "
            "`maglab setup <feature>` for the relevant feature before SSH or remote workflows."
        )
    if any(row["missing_external"] for row in feature_rows):
        next_actions.append(
            "Run `maglab setup <feature>` for solver, gateway, and TeX setup hints."
        )
    if not next_actions:
        next_actions.append("Open any research folder and run `maglab`.")

    return {
        "version": __version__,
        "python": {
            "status": python_status,
            "version": current_python,
            "executable": sys.executable,
            "recommended": "3.12",
        },
        "command": command_probe
        | {
            "invocation": str(Path(sys.argv[0]).resolve()) if sys.argv else "",
        },
        "installers": {
            "pipx": pipx_cmd,
            "uv": uv_cmd,
            "pip": pip_cmd,
        },
        "workspace": {
            "root": str(workspace.root),
            "project_state": str(workspace.local_state_dir),
            "global_config": str(platformdirs.user_config_dir("maglab")),
            "global_data": str(platformdirs.user_data_dir("maglab")),
            "global_cache": str(platformdirs.user_cache_dir("maglab")),
            "maglab_md": str(workspace.maglab_md) if workspace.maglab_md else None,
        },
        "features": feature_rows,
        "recommended_install": RECOMMENDED_INSTALL,
        "next_actions": next_actions,
    }


def render_install_commands(console: Console | None = None) -> None:
    """Render the global installation command summary."""
    con = console or Console()
    con.print("[bold]Global MagLab install[/]")
    con.print(f"  Recommended: [cyan]{escape(RECOMMENDED_INSTALL)}[/]")
    con.print(f"  uv tool:     [cyan]{escape(UV_TOOL_INSTALL)}[/]")
    con.print(f"  pipx:        [cyan]{escape(PIPX_INSTALL)}[/]")
    con.print()
    con.print(
        "After installation, open any research folder and run [bold]maglab[/]. "
        "MagLab will use that folder as the workspace while keeping config/data/cache in global app paths."
    )
    con.print("Run [cyan]maglab install doctor[/] to audit the active installation.")


def render_install_doctor(console: Console | None = None) -> dict[str, object]:
    """Render and return the installation preflight report."""
    con = console or Console()
    report = build_install_doctor_report()

    system = report["python"]
    command = report["command"]
    workspace = report["workspace"]
    installers = report["installers"]
    assert isinstance(system, dict)
    assert isinstance(command, dict)
    assert isinstance(workspace, dict)
    assert isinstance(installers, dict)

    table = Table(title="MagLab install doctor")
    table.add_column("Area", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_row(
        "python",
        str(system["status"]),
        f"{system['version']} at {system['executable']} (recommended {system['recommended']})",
    )
    table.add_row(
        "maglab command",
        str(command["status"]),
        f"{command['maglab'] or 'not found on PATH'} — {command['detail']}",
    )
    table.add_row(
        "installer",
        "ready" if installers["pipx"] or installers["uv"] else "missing",
        f"pipx={installers['pipx'] or '-'}  uv={installers['uv'] or '-'}",
    )
    table.add_row("workspace", "ready", str(workspace["root"]))
    table.add_row("global config", "ready", str(workspace["global_config"]))
    table.add_row(
        "global data/cache", "ready", f"{workspace['global_data']} · {workspace['global_cache']}"
    )
    con.print(table)

    feature_table = Table(title="Research extra coverage")
    feature_table.add_column("Feature", style="cyan")
    feature_table.add_column("Python")
    feature_table.add_column("Optional Python")
    feature_table.add_column("External")
    feature_table.add_column("Next")
    for row in cast(list[dict[str, Any]], report["features"]):
        missing_python = row["missing_python"]
        optional_python = row["optional_python"]
        missing_optional_python = row["missing_optional_python"]
        missing_external = row["missing_external"]
        assert isinstance(missing_python, list)
        assert isinstance(optional_python, dict)
        assert isinstance(missing_optional_python, list)
        assert isinstance(missing_external, list)
        optional_cell = "n/a"
        if optional_python:
            optional_cell = (
                "ready"
                if row["optional_python_ready"]
                else ", ".join(map(str, missing_optional_python))
            )
        feature_table.add_row(
            str(row["key"]),
            "ready" if row["python_ready"] else ", ".join(map(str, missing_python)),
            optional_cell,
            "ready" if row["external_ready"] else ", ".join(map(str, missing_external)),
            str(row["slash"]),
        )
    con.print(feature_table)

    con.print("[bold]Next actions[/]")
    for action in cast(list[str], report["next_actions"]):
        con.print(f"  - {escape(action)}")
    return report


def render_setup(feature_name: str | None = None, *, console: Console | None = None) -> None:
    """Render terminal setup guidance for one feature or all features."""
    con = console or Console()
    key = normalize_feature(feature_name)
    if key == "all":
        con.print("[bold]Recommended full research install[/]")
        con.print(f"  [cyan]{escape(RECOMMENDED_INSTALL)}[/]")
        con.print(f"  [dim]uv tool fallback:[/] {escape(UV_TOOL_INSTALL)}")
        con.print(f"  [dim]dev editable fallback:[/] {escape(DEV_INSTALL)}")
        con.print(f"  [dim]pip fallback:[/] {escape(PIP_INSTALL)}")
        con.print(
            "  [dim]dev editable fallback keeps the command tied to this clone; pipx/uv tool is global.[/]"
        )
        con.print()
        render_feature_table(con)
        con.print("\nUse [cyan]/setup <feature>[/] or [cyan]maglab setup <feature>[/] for details.")
        return
    feature = FEATURES.get(key)
    if feature is None:
        con.print(f"[red]Unknown setup feature:[/] {feature_name!r}")
        con.print(f"Available: all, {', '.join(list_feature_keys())}")
        return

    con.print(f"[bold]{feature.title}[/]")
    install_cmd = f'pipx inject maglab "maglab[{feature.extra}]"'
    dev_install_cmd = f'uv pip install -e ".[{feature.extra}]"'
    con.print(f"  Install extra into global app: [cyan]{escape(install_cmd)}[/]")
    con.print(f"  Dev editable fallback: [cyan]{escape(dev_install_cmd)}[/]")
    con.print(f"  Recommended all-in-one: [cyan]{escape(RECOMMENDED_INSTALL)}[/]")
    con.print(f"  REPL slash: [cyan]{feature.slash}[/] or [cyan]/setup {feature.key}[/]")

    import_status = _status_line(feature.imports, _module_ok)
    if import_status:
        con.print("  Python packages:")
        for line in import_status:
            con.print(f"    {line}")
    optional_import_status = _status_line(feature.optional_imports, _module_ok)
    if optional_import_status:
        con.print("  Optional Python packages:")
        for line in optional_import_status:
            con.print(f"    {line}")
    binary_status = _status_line(feature.binaries, _binary_ok)
    if binary_status:
        con.print("  External tools:")
        for line in binary_status:
            con.print(f"    {line}")
    if feature.setup_commands:
        con.print("  Terminal setup/check commands:")
        for cmd in feature.setup_commands:
            con.print(f"    [cyan]{cmd}[/]")
    if feature.notes:
        con.print("  Notes:")
        for note in feature.notes:
            con.print(f"    {note}")


def render_feature_table(console: Console | None = None) -> None:
    """Render a compact table of setup features."""
    con = console or Console()
    table = Table(title="MagLab research feature setup")
    table.add_column("Feature", style="cyan")
    table.add_column("Extra")
    table.add_column("Slash")
    table.add_column("Python")
    table.add_column("Optional")
    table.add_column("External")
    for feature in FEATURES.values():
        table.add_row(
            feature.key,
            feature.extra,
            feature.slash,
            _compact_status(feature.imports, _module_ok),
            _compact_status(feature.optional_imports, _module_ok),
            _compact_status(feature.binaries, _binary_ok),
        )
    con.print(table)
