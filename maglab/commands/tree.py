"""Shared MagLab command tree metadata.

The REPL slash-command completer and ``/help`` renderer both read from this
module so the interactive surface stays aligned with the Typer CLI.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.tree import Tree

CommandTree = dict[str, Any]


FEATURE_KEYS: tuple[str, ...] = (
    "all",
    "llm",
    "literature",
    "simulation",
    "figure",
    "instrument",
    "authoring",
    "review",
    "gateway",
    "mcp",
)


_BASE_SLASH_COMMANDS: CommandTree = {
    "/help": {
        "quick": None,
        "all": None,
        "workspace": None,
        "llm": None,
        "sim": None,
        "figure": None,
        "literature": None,
    },
    "/clear": None,
    "/quit": None,
    "/exit": None,
    "/reset": {"config": None, "defaults": None},
    "/workspace": {"status": None, "init": None, "tree": None, "brief": None},
    "/install": None,
    "/manual": {"en": None, "ko": None},
    "/doctor": None,
    "/setup": dict.fromkeys(FEATURE_KEYS),
    **{f"/setup-{key}": None for key in FEATURE_KEYS if key != "all"},
    "/connect": {
        "status": None,
        "reset": None,
        "defaults": None,
        "codex": None,
        "claude": None,
        "gemini-cli": None,
        "anthropic": None,
        "grok": None,
        "deepseek": None,
        "qwen": None,
        "kimi": None,
        "gemini": None,
        "openai": None,
        "openai-compatible": None,
        "api": None,
        "ollama": None,
    },
    "/auth": {
        "set": None,
        "list": None,
        "test": None,
        "status": None,
        "anthropic": None,
        "grok": None,
        "deepseek": None,
        "qwen": None,
        "kimi": None,
        "gemini": None,
        "openai": None,
        "openai-compatible": None,
        "codex": None,
        "claude": None,
        "gemini-cli": None,
        "ollama": None,
    },
    "/physics": {"compute": None, "units": None, "oracle": None},
    "/mat": {"list": None, "show": None, "search": None, "build": None},
    "/theme": {
        "list": None,
        "set": None,
        "domain": None,
        "mono": None,
        "moke": None,
        "light": None,
    },
    "/skill": {"list": None, "create": None, "install": None},
    "/cost": None,
    "/mcp": {"list": None, "serve": None, "add": None, "enable": None, "disable": None},
    "/agents": {"list": None, "show": None},
    "/config": {"show": None, "path": None, "reset": None, "restore": None},
    "/report": {"inventory": None},
    "/prov": {"summary": None, "status": None},
    "/task": {"list": None, "status": None, "scaffold": None},
    "/version": None,
    "/info": None,
    "/ask": None,
    "/run": None,
    "/sim": {
        "doctor": None,
        "micro": None,
        "validate": None,
        "plot": None,
        "job": None,
        "dft": None,
        "atomistic": None,
        "pipeline": None,
    },
    "/figure": {
        "spec": None,
        "render": None,
        "compose": None,
        "export": None,
        "primitives": {"list": None, "show": None, "ingest": None},
    },
    "/instr": {
        "scaffold": None,
        "scpi": None,
        "script": None,
        "check": None,
        "ingest": None,
        "skillgen": None,
        "implement": None,
    },
    "/fit": None,
    "/analyze": {"load": None, "model": None, "consistency": None, "symmetry": None},
    "/device": {"fom": None},
    "/ralph": {"start": None, "status": None, "cancel": None},
    "/lit": {"search": None, "authors": None, "keywords": None, "journal": None, "graph": None},
    "/review": None,
    "/lab": {"note": None, "note-list": None, "plan": None},
    "/explain": None,
    "/write": None,
    "/comms": {
        "revision": None,
        "cover-letter": None,
        "email": None,
        "abstract": None,
        "grant": None,
        "rebuttal": None,
    },
    "/gateway": {"setup": None, "start": None, "stop": None, "status": None, "install": None},
    "/present": {
        "templates": {"--detail": None, "--kind": {"all": None, "slides": None, "poster": None}},
        "slides": None,
        "poster": None,
    },
    "/hypotheses": None,
}


CLI_SLASH_ROOTS: frozenset[str] = frozenset(
    cmd
    for cmd in _BASE_SLASH_COMMANDS
    if cmd
    not in {
        "/help",
        "/clear",
        "/quit",
        "/exit",
        "/connect",
        "/reset",
    }
)


@dataclass(frozen=True)
class HelpEntry:
    """One row in the human-readable slash command tree."""

    label: str
    description: str
    children: tuple[HelpEntry, ...] = field(default_factory=tuple)


HELP_SECTIONS: tuple[HelpEntry, ...] = (
    HelpEntry(
        "Session",
        "interactive shell controls",
        (
            HelpEntry("/help quick|all|<area>", "show quick, full, or area-specific help"),
            HelpEntry("/clear", "clear the terminal"),
            HelpEntry("/reset config", "restore the previous config backup"),
            HelpEntry("/reset defaults", "write a clean default config"),
            HelpEntry("/quit, /exit", "leave the REPL"),
        ),
    ),
    HelpEntry(
        "Install and workspace",
        "global command plus per-folder workspace",
        (
            HelpEntry("/install", "print global install commands"),
            HelpEntry("/manual --lang en|ko", "list installed user manuals"),
            HelpEntry("/doctor", "check workspace, backend, package extras, and sim readiness"),
            HelpEntry("/workspace status", "show current folder, config, data, cache paths"),
            HelpEntry("/workspace brief", "summarize the active folder in one screen"),
            HelpEntry("/workspace init", "create a local MAGLAB.md workspace marker"),
            HelpEntry("/workspace tree", "show the files MagLab sees in this folder"),
            HelpEntry("/setup <feature>", "show package and external-tool setup guidance"),
            HelpEntry("/report inventory", "list generated manuscript, slide, and poster files"),
            HelpEntry("/prov summary", "list provenance sidecars and optional W3C PROV DB stats"),
            HelpEntry("/task list|status|scaffold", "inspect checkpoints and create task files"),
            HelpEntry("/ask <query>", "run one non-interactive MagLab turn"),
            HelpEntry("/run <goal>", "start the research-loop tree search"),
        ),
    ),
    HelpEntry(
        "LLM backend",
        "secret-safe provider and model setup",
        (
            HelpEntry("/connect status", "inspect current backend readiness"),
            HelpEntry("/connect codex|claude|gemini-cli", "use delegated CLI OAuth"),
            HelpEntry(
                "/connect anthropic|grok|deepseek|qwen|kimi|gemini|openai",
                "configure direct API key backend",
            ),
            HelpEntry(
                "/connect api <provider> [model] [base_url]", "configure provider explicitly"
            ),
            HelpEntry("/connect ollama [model] [host]", "use local Ollama"),
            HelpEntry("/auth ...", "same credential commands as the CLI"),
        ),
    ),
    HelpEntry(
        "Research primitives",
        "deterministic science tools",
        (
            HelpEntry("/physics compute|units|oracle", "formula, unit, and sanity checks"),
            HelpEntry("/mat list|show|search|build", "materials database and stack builder"),
            HelpEntry(
                "/sim doctor|micro|validate|plot|job|dft|atomistic|pipeline",
                "simulation workflows and backend readiness",
            ),
            HelpEntry("/analyze load|model|consistency|symmetry", "data/model consistency checks"),
            HelpEntry("/device fom", "device figure-of-merit calculations"),
        ),
    ),
    HelpEntry(
        "Literature and writing",
        "paper discovery, lab notes, and authoring",
        (
            HelpEntry("/lit search|authors|keywords|journal|graph", "literature intelligence"),
            HelpEntry("/lab note|note-list|plan", "ELN and measurement planning"),
            HelpEntry("/review", "persona review panel"),
            HelpEntry("/explain", "anomaly explanation"),
            HelpEntry("/write", "journal manuscript drafting"),
            HelpEntry(
                "/comms revision|cover-letter|email|abstract|grant|rebuttal",
                "academic communications",
            ),
        ),
    ),
    HelpEntry(
        "Figures, instruments, automation",
        "deliverables and external interfaces",
        (
            HelpEntry(
                "/figure spec|render|compose|export|primitives ingest",
                "figure production and primitive review catalog",
            ),
            HelpEntry(
                "/instr scaffold|scpi|script|check|ingest|skillgen|implement",
                "instrument and manual workflows",
            ),
            HelpEntry("/skill list|create|install", "workspace-local skill packages"),
            HelpEntry("/mcp list|serve|add|enable|disable", "MCP tools"),
            HelpEntry("/agents list|show", "subagent definitions"),
            HelpEntry("/ralph start|status|cancel", "autonomous loop engine"),
            HelpEntry("/gateway setup|start|stop|status|install", "messaging gateway"),
            HelpEntry("/present templates|slides|poster", "presentation materials"),
            HelpEntry("/hypotheses", "hypothesis generation"),
        ),
    ),
)

QUICK_HELP: tuple[HelpEntry, ...] = (
    HelpEntry("/doctor", "check local readiness; add --smoke for live LLM verification"),
    HelpEntry("/workspace brief", "summarize the current folder"),
    HelpEntry("/connect status", "inspect the selected model/backend"),
    HelpEntry("/sim doctor", "choose mock, CPU, local GPU, SSH GPU, or SSH HPC path"),
    HelpEntry("/manual ko orchestration", "open the Korean orchestration manual"),
    HelpEntry("normal prompt", 'ask naturally, e.g. "Read README and suggest first run steps"'),
)

AREA_ALIASES: dict[str, tuple[str, ...]] = {
    "workspace": ("Install and workspace",),
    "llm": ("LLM backend",),
    "sim": ("Research primitives",),
    "simulation": ("Research primitives",),
    "figure": ("Figures, instruments, automation",),
    "figures": ("Figures, instruments, automation",),
    "literature": ("Literature and writing",),
    "writing": ("Literature and writing",),
}


def base_slash_commands() -> CommandTree:
    """Return a mutable copy of the slash completion tree."""
    return deepcopy(_BASE_SLASH_COMMANDS)


def render_slash_help(console: Console | None = None) -> None:
    """Render the slash command tree."""
    con = console or Console()
    root = Tree("[bold]MagLab slash command tree[/]")
    for section in HELP_SECTIONS:
        section_node = root.add(f"[cyan]{section.label}[/] - {section.description}")
        for entry in section.children:
            _add_help_entry(section_node, entry)
    con.print(root)
    con.print()
    con.print(
        "[dim]Anything not starting with / is sent to the MagLab orchestrator as a normal prompt.[/]"
    )


def render_quick_help(console: Console | None = None) -> None:
    """Render a one-screen first-run command guide."""
    con = console or Console()
    root = Tree("[bold]MagLab quick help[/]")
    for entry in QUICK_HELP:
        _add_help_entry(root, entry)
    con.print(root)
    con.print()
    con.print("[dim]Use /help all for the full command tree or /help <area> for a section.[/]")


def render_area_help(area: str, console: Console | None = None) -> bool:
    """Render one help area. Returns False when the area is unknown."""
    con = console or Console()
    wanted = AREA_ALIASES.get(area.lower())
    if not wanted:
        return False
    root = Tree(f"[bold]MagLab help: {area.lower()}[/]")
    for section in HELP_SECTIONS:
        if section.label not in wanted:
            continue
        section_node = root.add(f"[cyan]{section.label}[/] - {section.description}")
        for entry in section.children:
            _add_help_entry(section_node, entry)
    con.print(root)
    return True


def _add_help_entry(parent: Tree, entry: HelpEntry) -> None:
    node = parent.add(f"[bold]{entry.label}[/] - {entry.description}")
    for child in entry.children:
        _add_help_entry(node, child)
