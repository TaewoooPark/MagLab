"""Terminal setup registry for MagLab research features.

The registry centralizes optional dependency extras, terminal setup commands,
and slash command names. It does not install packages automatically; it gives
the exact command and then keeps feature-specific configuration inside MagLab's
terminal flow.
"""

from __future__ import annotations

import importlib.util
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from rich.console import Console
from rich.markup import escape
from rich.table import Table

RECOMMENDED_INSTALL = 'pipx install --editable ".[research]"'
UV_TOOL_INSTALL = 'uv tool install --editable ".[research]"'
PIPX_INSTALL = 'pipx install --editable ".[research]"'
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
        binaries=("mumax3", "oommf"),
        setup_commands=(
            "maglab sim validate examples/sim/micro.yaml",
            "maglab sim pipeline --structure bcc_fe --scales dft,atomistic,micro,device --backend mock",
        ),
        notes=(
            "Python simulation libraries install through the research extra.",
            "External solvers such as MuMax3/OOMMF still need system installation when not using mock mode.",
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
    table.add_column("Purpose")
    for feature in FEATURES.values():
        table.add_row(feature.key, feature.extra, feature.slash, feature.title)
    con.print(table)
