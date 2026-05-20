"""maglab CLI application — Typer app + Appendix A subcommand tree.

P0 available commands: auth · physics · mat · theme · skill · cost · mcp · agents ·
                       config · version · info.
P1 available commands: sim (micro·validate·plot·job) · figure (spec·render·compose·export).
Subsequent Phase commands are registered as honest stubs (exit 0, prints Phase number).

Running with no arguments → ``maglab.repl.run_repl(config)`` (interactive REPL).
"""

from __future__ import annotations

import sys
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from maglab import __version__
from maglab.commands import p2_analysis, p4_ralph, p5_literature, p6_authoring
from maglab.config import Config, load_config

# ---------------------------------------------------------------------------
# App & console
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="maglab",
    help="AI for Science harness for magnetism and spintronics research.",
    no_args_is_help=False,
    add_completion=False,
    invoke_without_command=True,
)
console = Console()


def _build_orchestrator(config: Config) -> Any:
    """Create an orchestrator for one CLI invocation."""
    from maglab.core.orchestrator import Orchestrator
    from maglab.llm.base import ModelRouter
    from maglab.llm.factory import create_llm_backend

    backend = create_llm_backend(config)
    model_router = (
        ModelRouter(config.routing.model_dump()) if config.backend.mode == "api" else None
    )
    try:
        return Orchestrator(
            config=config,
            backend=backend,
            model_router=model_router,
        )
    except TypeError:
        return Orchestrator(config=config, backend=backend)


def _print_prompt_response(prompt: str) -> None:
    """Run one non-interactive MagLab turn and print the response."""
    config = load_config()
    orchestrator = _build_orchestrator(config)
    try:
        console.print(orchestrator.respond(prompt))
    finally:
        close = getattr(orchestrator, "close", None)
        if callable(close):
            close()


# ---------------------------------------------------------------------------
# No-argument invocation → REPL
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def _root_callback(
    ctx: typer.Context,
    prompt: str | None = typer.Option(
        None,
        "-p",
        "--prompt",
        help="Non-interactive single query (for pipe / CI use).",
    ),
) -> None:
    """Start the interactive REPL when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return
    if prompt is not None:
        _print_prompt_response(prompt)
        return
    # Interactive REPL
    config = load_config()
    from maglab.repl import run_repl  # deferred import (show banner first)

    run_repl(config)


# ===========================================================================
# P0 available commands
# ===========================================================================


@app.command("ask")
def ask_cmd(
    query: str = typer.Argument(..., help="Natural-language prompt for one MagLab turn."),
) -> None:
    """Run one non-interactive natural-language MagLab turn."""
    _print_prompt_response(query)


@app.command("run")
def run_cmd(
    goal: str = typer.Argument(..., help="Autonomous research-loop goal."),
) -> None:
    """Start the MagLab research-loop tree search for a goal."""
    config = load_config()
    orchestrator = _build_orchestrator(config)
    try:
        result = orchestrator.run(goal)
    finally:
        close = getattr(orchestrator, "close", None)
        if callable(close):
            close()

    table = Table(title="MagLab run")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("status", result.status)
    table.add_row("summary", result.summary)
    if result.datapoints:
        table.add_row("datapoints", "\n".join(result.datapoints))
    if result.warnings:
        table.add_row("warnings", "\n".join(result.warnings))
    console.print(table)


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

auth_app = typer.Typer(
    name="auth", help="LLM credential management (API key · delegated CLI · local)."
)
app.add_typer(auth_app)


@auth_app.command("set")
def auth_set(
    provider: str = typer.Argument(
        ...,
        help="Provider name (anthropic·grok·deepseek·qwen·kimi·gemini·openai·openai-compatible).",
    ),
    api_key: str | None = typer.Argument(None, help="API key string. Omit for hidden input."),
) -> None:
    """Store an API key in the keyring or auth.json."""
    import getpass

    from maglab.llm.auth import store_api_key
    from maglab.llm.providers import normalize_provider

    provider = normalize_provider(provider)
    if api_key is None:
        api_key = getpass.getpass(f"{provider} API key: ")
    if not api_key:
        console.print("[red]No API key provided.[/]")
        raise typer.Exit(1)
    location = store_api_key(provider, api_key)
    console.print(
        f"[green]✓[/] API key saved — provider=[bold]{provider}[/]  location=[bold]{location}[/]"
    )


@auth_app.command("list")
def auth_list() -> None:
    """List providers for which credentials are stored."""
    from maglab.llm.auth import list_providers

    found = list_providers()
    if not found:
        console.print("[dim]No credentials registered.[/]")
    else:
        for p in found:
            console.print(f"  [green]✓[/] {p}")


@auth_app.command("test")
def auth_test(
    provider: str | None = typer.Argument(
        None,
        help="Provider name to test. Omit to test the configured backend.",
    ),
    model: str | None = typer.Option(None, "--model", help="Model identifier to use for the test."),
) -> None:
    """Verify API credentials or configured delegated/local backend readiness."""
    if provider is None:
        from maglab import config as config_mod
        from maglab.llm.factory import test_llm_backend

        config = config_mod.load_config()
        status = test_llm_backend(config)
        if status.ok:
            console.print(f"[green]✓[/] Backend ready — [bold]{status.label}[/]")
            console.print(f"  {status.detail}")
            return
        console.print(f"[red]✗[/] Backend not ready — {status.detail}")
        if status.action:
            console.print(status.action)
        raise typer.Exit(code=1)

    from maglab.llm.auth import verify_connection
    from maglab.llm.providers import normalize_provider

    provider = normalize_provider(provider)
    with console.status(f"[dim]Testing connection ({provider})…[/]"):
        result = verify_connection(provider, model)
    if result["ok"]:
        console.print(
            f"[green]✓[/] Connection successful — provider=[bold]{provider}[/]  model=[bold]{result['model']}[/]"
        )
    else:
        console.print(f"[red]✗[/] Connection failed — {result['error']}")
        raise typer.Exit(code=1)


@auth_app.command("status")
def auth_status() -> None:
    """Show the configured LLM backend status without printing secrets."""
    from maglab import config as config_mod
    from maglab.llm.factory import backend_status

    config = config_mod.load_config()
    status = backend_status(config)
    marker = "[green]✓[/]" if status.ok else "[red]✗[/]"
    console.print(f"{marker} [bold]{status.label}[/]")
    console.print(f"  mode: {status.mode}")
    console.print(f"  config: {config_mod.config_path()}")
    console.print(f"  detail: {status.detail}")
    if status.action:
        console.print(f"  next: {status.action}")


def _configure_api_provider(
    provider: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    store_key: bool = True,
) -> None:
    """Configure a direct API provider and optionally capture its key securely."""
    import getpass

    from maglab import config as config_mod
    from maglab.llm.auth import get_api_key, store_api_key
    from maglab.llm.connect import configure_api_backend
    from maglab.llm.providers import get_provider_profile, normalize_provider

    provider = normalize_provider(provider)
    profile = get_provider_profile(provider)
    config = config_mod.load_config()
    if model is None:
        from maglab.ui.prompt import prompt_model_choice

        model = prompt_model_choice(provider)
    saved = configure_api_backend(
        config,
        provider=provider,
        model=model,
        base_url=base_url,
        path=config_mod.config_path(),
    )
    console.print(
        f"[green]✓[/] Configured [bold]{profile.title}[/] API backend in [bold]{saved}[/]."
    )

    if store_key:
        existing = get_api_key(provider)
        suffix = "blank to keep existing" if existing else "blank to skip storing"
        api_key = getpass.getpass(f"{profile.title} API key ({suffix}): ")
        if api_key:
            location = store_api_key(provider, api_key)
            console.print(f"[green]✓[/] API key saved in [bold]{location}[/].")

    console.print(
        f"Restart MagLab to load this backend. Default model: [bold]{config.backend.api.model}[/]"
    )


@auth_app.command("anthropic")
def auth_anthropic(
    model: str | None = typer.Option(None, "--model", "-m", help="Anthropic model."),
    store_key: bool = typer.Option(True, "--store-key/--no-store-key", help="Prompt for API key."),
) -> None:
    """Use an Anthropic API key as the MagLab backend."""
    _configure_api_provider("anthropic", model=model, store_key=store_key)


@auth_app.command("grok")
def auth_grok(
    model: str | None = typer.Option(None, "--model", "-m", help="xAI/Grok model."),
    store_key: bool = typer.Option(True, "--store-key/--no-store-key", help="Prompt for API key."),
) -> None:
    """Use an xAI/Grok API key as the MagLab backend."""
    _configure_api_provider("grok", model=model, store_key=store_key)


@auth_app.command("deepseek")
def auth_deepseek(
    model: str | None = typer.Option(None, "--model", "-m", help="DeepSeek model."),
    store_key: bool = typer.Option(True, "--store-key/--no-store-key", help="Prompt for API key."),
) -> None:
    """Use a DeepSeek API key as the MagLab backend."""
    _configure_api_provider("deepseek", model=model, store_key=store_key)


@auth_app.command("qwen")
def auth_qwen(
    model: str | None = typer.Option(None, "--model", "-m", help="Qwen/DashScope model."),
    store_key: bool = typer.Option(True, "--store-key/--no-store-key", help="Prompt for API key."),
) -> None:
    """Use a Qwen/DashScope API key as the MagLab backend."""
    _configure_api_provider("qwen", model=model, store_key=store_key)


@auth_app.command("kimi")
def auth_kimi(
    model: str | None = typer.Option(None, "--model", "-m", help="Kimi/Moonshot model."),
    store_key: bool = typer.Option(True, "--store-key/--no-store-key", help="Prompt for API key."),
) -> None:
    """Use a Kimi/Moonshot API key as the MagLab backend."""
    _configure_api_provider("kimi", model=model, store_key=store_key)


@auth_app.command("gemini")
def auth_gemini(
    model: str | None = typer.Option(None, "--model", "-m", help="Gemini API model."),
    store_key: bool = typer.Option(True, "--store-key/--no-store-key", help="Prompt for API key."),
) -> None:
    """Use a Gemini API key as the MagLab backend."""
    _configure_api_provider("gemini", model=model, store_key=store_key)


@auth_app.command("openai")
def auth_openai(
    model: str | None = typer.Option(None, "--model", "-m", help="OpenAI model."),
    store_key: bool = typer.Option(True, "--store-key/--no-store-key", help="Prompt for API key."),
) -> None:
    """Use an OpenAI API key as the MagLab backend."""
    _configure_api_provider("openai", model=model, store_key=store_key)


@auth_app.command("openai-compatible")
def auth_openai_compatible(
    model: str | None = typer.Option(None, "--model", "-m", help="Endpoint model name."),
    base_url: str = typer.Option(..., "--base-url", help="OpenAI-compatible /v1 endpoint URL."),
    store_key: bool = typer.Option(True, "--store-key/--no-store-key", help="Prompt for API key."),
) -> None:
    """Use an OpenAI-compatible endpoint as the MagLab backend."""
    _configure_api_provider(
        "openai-compatible",
        model=model,
        base_url=base_url,
        store_key=store_key,
    )


@auth_app.command("codex")
def auth_codex(
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Optional Codex model. Omit to use the official CLI default.",
    ),
) -> None:
    """Use the officially authenticated Codex CLI as the MagLab backend."""
    from maglab import config as config_mod
    from maglab.llm.connect import configure_delegated_cli
    from maglab.ui.prompt import prompt_delegated_model_choice

    config = config_mod.load_config()
    model = prompt_delegated_model_choice("codex", model)
    saved, exe_status = configure_delegated_cli(
        config, tool="codex", model=model, path=config_mod.config_path()
    )
    console.print(f"[green]✓[/] Configured Codex delegated CLI backend in [bold]{saved}[/].")
    if exe_status == "missing":
        console.print(
            "[yellow]Codex CLI was not found on PATH.[/] Install and authenticate the official "
            "Codex CLI first, then restart MagLab."
        )
    else:
        console.print(
            "Codex CLI executable found. If it is not already authenticated, complete the "
            "official Codex login flow, then restart MagLab."
        )


@auth_app.command("claude")
def auth_claude(
    model: str | None = typer.Option(None, "--model", "-m", help="Optional Claude model."),
) -> None:
    """Use the officially authenticated Claude CLI as the MagLab backend."""
    from maglab import config as config_mod
    from maglab.llm.connect import configure_delegated_cli
    from maglab.ui.prompt import prompt_delegated_model_choice

    config = config_mod.load_config()
    model = prompt_delegated_model_choice("claude", model)
    saved, exe_status = configure_delegated_cli(
        config, tool="claude", model=model, path=config_mod.config_path()
    )
    console.print(f"[green]✓[/] Configured Claude delegated CLI backend in [bold]{saved}[/].")
    if exe_status == "missing":
        console.print(
            "[yellow]Claude CLI was not found on PATH.[/] Install/authenticate it, then restart MagLab."
        )
    else:
        console.print("Claude CLI executable found. Restart MagLab to use it.")


@auth_app.command("gemini-cli")
def auth_gemini_cli(
    model: str | None = typer.Option(None, "--model", "-m", help="Optional Gemini model."),
) -> None:
    """Use the officially authenticated Gemini CLI as the MagLab backend."""
    from maglab import config as config_mod
    from maglab.llm.connect import configure_delegated_cli
    from maglab.ui.prompt import prompt_delegated_model_choice

    config = config_mod.load_config()
    model = prompt_delegated_model_choice("gemini", model)
    saved, exe_status = configure_delegated_cli(
        config, tool="gemini", model=model, path=config_mod.config_path()
    )
    console.print(f"[green]✓[/] Configured Gemini delegated CLI backend in [bold]{saved}[/].")
    if exe_status == "missing":
        console.print(
            "[yellow]Gemini CLI was not found on PATH.[/] Install/authenticate it, then restart MagLab."
        )
    else:
        console.print("Gemini CLI executable found. Restart MagLab to use it.")


@auth_app.command("ollama")
def auth_ollama(
    model: str = typer.Option("llama3.1", "--model", "-m", help="Ollama model name."),
    host: str = typer.Option("http://localhost:11434", "--host", help="Ollama server URL."),
) -> None:
    """Use a local Ollama model as the MagLab backend."""
    from maglab import config as config_mod
    from maglab.llm.connect import configure_local_backend

    config = config_mod.load_config()
    saved = configure_local_backend(config, model=model, host=host, path=config_mod.config_path())
    console.print(f"[green]✓[/] Configured Ollama backend in [bold]{saved}[/].")
    console.print("Start Ollama with `ollama serve`, then restart MagLab.")


# ---------------------------------------------------------------------------
# physics
# ---------------------------------------------------------------------------

physics_app = typer.Typer(
    name="physics", help="Deterministic physics calculations (formulas · units · oracle)."
)
app.add_typer(physics_app)


_PARAMS_ARG = typer.Argument(None, help="Parameter key=value list.")


@physics_app.command("compute")
def physics_compute(
    formula: str = typer.Argument(
        ..., help="Formula name (exchange_length·bloch_wall_width, etc.)."
    ),
    params: list[str] | None = _PARAMS_ARG,
) -> None:
    """Compute a physics quantity using a deterministic formula."""
    from maglab.physics import formulas as _f

    # Parse parameters
    kw: dict[str, float] = {}
    for item in params or []:
        if "=" in item:
            k, v = item.split("=", 1)
            try:
                kw[k.strip()] = float(v.strip())
            except ValueError:
                console.print(f"[red]Parameter parse error:[/] {item}")
                raise typer.Exit(1) from None

    fn = getattr(_f, formula, None)
    if fn is None:
        available = [n for n in dir(_f) if not n.startswith("_") and callable(getattr(_f, n))]
        console.print(f"[red]Unknown formula:[/] {formula!r}")
        console.print(f"Available: {', '.join(available[:20])}")
        raise typer.Exit(1)

    try:
        result = fn(**kw)
        console.print(
            f"[cyan]{formula}[/]({', '.join(f'{k}={v}' for k, v in kw.items())}) = [bold]{result}[/]"
        )
    except Exception as exc:
        console.print(f"[red]Calculation error:[/] {exc}")
        raise typer.Exit(1) from exc


@physics_app.command("units")
def physics_units(
    value: float = typer.Argument(..., help="Value to convert."),
    from_unit: str = typer.Argument(..., help="Source unit (e.g. Oe, emu_cm3)."),
    to_unit: str = typer.Argument(..., help="Target unit (e.g. Am, Am)."),
) -> None:
    """Perform a magnetic unit conversion."""
    from maglab.physics import units as _u

    fn_name = f"{from_unit}_to_{to_unit}"
    fn = getattr(_u, fn_name, None)
    if fn is None:
        # Try reverse direction
        fn_name_rev = f"{to_unit}_to_{from_unit}"
        if getattr(_u, fn_name_rev, None):
            console.print(f"[yellow]Hint:[/] Reverse function {fn_name_rev!r} exists.")
        console.print(f"[red]Unit conversion function not found:[/] {fn_name!r}")
        raise typer.Exit(1)

    try:
        result = fn(value)
        console.print(f"{value} {from_unit} = [bold]{result}[/] {to_unit}")
    except Exception as exc:
        console.print(f"[red]Conversion error:[/] {exc}")
        raise typer.Exit(1) from exc


@physics_app.command("oracle")
def physics_oracle(
    params: list[str] | None = _PARAMS_ARG,
) -> None:
    """Check the sanity of physics parameters using the oracle."""
    from maglab.physics.oracle import check

    kw: dict[str, float] = {}
    for item in params or []:
        if "=" in item:
            k, v = item.split("=", 1)
            try:
                kw[k.strip()] = float(v.strip())
            except ValueError:
                console.print(f"[red]Parameter parse error:[/] {item}")
                raise typer.Exit(1) from None

    if not kw:
        console.print("[dim]Usage: maglab physics oracle alpha=0.01 Ms=800000[/]")
        return

    result = check(kw)
    if result.ok:
        console.print(f"[green]✓[/] Physically valid. (checks passed: {', '.join(result.checks)})")
    else:
        console.print(
            f"[red]✗[/] Unphysical: {result.reason}  (param={result.param!r}, value={result.value})"
        )


# ---------------------------------------------------------------------------
# mat
# ---------------------------------------------------------------------------

mat_app = typer.Typer(name="mat", help="Magnetic material database.")
app.add_typer(mat_app)


@mat_app.command("list")
def mat_list() -> None:
    """Print the list of registered materials."""
    from maglab.physics.materials import list_materials

    mats = list_materials()
    table = Table(title="Magnetic Material Database", show_lines=False)
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Formula")
    table.add_column("Structure")
    for m in mats:
        table.add_row(m.id, m.name, m.formula, m.structure)
    console.print(table)


@mat_app.command("show")
def mat_show(
    material_id: str = typer.Argument(..., help="Material ID (e.g. Permalloy, YIG)."),
) -> None:
    """Print detailed material properties."""
    from maglab.physics.materials import lookup

    mat = lookup(material_id)
    if mat is None:
        console.print(f"[red]Material not found:[/] {material_id!r}")
        raise typer.Exit(1)

    table = Table(title=f"{mat.name} ({mat.id})", show_lines=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_column("Unit")

    def _row(label: str, val: object, unit: str) -> None:
        table.add_row(label, str(val) if val is not None else "[dim]N/A[/]", unit)

    _row("Formula", mat.formula, "")
    _row("Structure", mat.structure, "")
    _row("Saturation magnetization Ms", mat.Ms_Am, "A/m")
    _row("Exchange stiffness A", mat.A_Jm, "J/m")
    _row("Anisotropy constant K", mat.K_Jm3, "J/m³")
    _row("Gilbert damping α", mat.alpha, "")
    _row("Curie temperature T_C", mat.T_C_K, "K")
    _row("g-factor", mat.g_factor, "")
    _row("Source DOI", mat.source_doi, "")
    console.print(table)
    if mat.notes:
        console.print(f"[dim]{mat.notes}[/]")


@mat_app.command("build")
def mat_build(
    stack: str = typer.Argument(..., help='Layer stack string, e.g. "Ta(5)/CoFeB(1)/MgO(2)".'),
    online: bool = typer.Option(
        False, "--online", help="Query online databases (Materials Project / OPTIMADE)."
    ),
    save: bool = typer.Option(
        False, "--save", help="Append the built layers to the materials database YAML."
    ),
) -> None:
    """Build per-layer material property DataPoints from a stack string (F5).

    Every property value is sourced from a database or the literature with a
    DOI — never generated by the LLM.
    """
    from maglab.physics.material_builder import build_material_stack, save_to_materials_yaml

    try:
        result = build_material_stack(stack, use_mp=online, use_optimade=online)
    except ValueError as exc:
        console.print(f"[red]Stack parse error:[/] {exc}")
        raise typer.Exit(1) from exc

    table = Table(title=f"Material stack: {result.stack_str}", show_lines=True)
    table.add_column("Layer", style="cyan")
    table.add_column("Property")
    table.add_column("Value")
    table.add_column("Source")
    for ld in result.layers:
        if not ld.datapoints:
            table.add_row(ld.layer.material, "[dim]no data[/]", "", ld.source_info or "—")
            continue
        for prop_name, dp in ld.datapoints.items():
            table.add_row(ld.layer.material, prop_name, str(dp.value), ld.source_info or "—")
    console.print(table)

    for warn in result.warnings:
        console.print(f"  [yellow]warning:[/] {warn}")

    if save:
        path = save_to_materials_yaml(result)
        console.print(f"[green]✓[/] Appended to {path}")


# ---------------------------------------------------------------------------
# theme
# ---------------------------------------------------------------------------

theme_app = typer.Typer(name="theme", help="Terminal theme management.")
app.add_typer(theme_app)


@theme_app.command("list")
def theme_list() -> None:
    """Print the list of available themes."""
    from maglab.ui.theme import Theme

    themes = Theme.available_themes()
    console.print("[bold]Bundled themes:[/]")
    for t in themes:
        console.print(f"  • {t}")


@theme_app.command("set")
def theme_set(
    name: str = typer.Argument(..., help="Theme name (domain·mono·moke·light)."),
) -> None:
    """Change the active theme (current session + config save)."""
    from maglab.ui.theme import Theme

    try:
        Theme.load(name)
    except FileNotFoundError:
        console.print(f"[red]Unknown theme:[/] {name!r}")
        console.print(f"Available: {', '.join(Theme.available_themes())}")
        raise typer.Exit(1) from None

    # Update config
    import tomllib

    from maglab.config import config_path

    cfg_path = config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing TOML
    raw: dict = {}
    if cfg_path.is_file():
        with cfg_path.open("rb") as fh:
            raw = tomllib.load(fh)

    raw.setdefault("ui", {})["theme"] = name

    # tomllib is read-only; use tomli_w or direct serialization
    try:
        import tomli_w  # type: ignore[import-untyped]

        cfg_path.write_text(tomli_w.dumps(raw), encoding="utf-8")
    except ImportError:
        # Fallback: hand-serialise the full `raw` dict so no keys are dropped.
        lines_out: list[str] = []
        for section, vals in raw.items():
            if isinstance(vals, dict):
                lines_out.append(f"[{section}]")
                for k, v in vals.items():
                    if isinstance(v, str):
                        lines_out.append(f'{k} = "{v}"')
                    else:
                        lines_out.append(f"{k} = {v}")
                lines_out.append("")
        cfg_path.write_text("\n".join(lines_out), encoding="utf-8")

    console.print(f"[green]✓[/] Theme set to [bold]{name}[/].")


# ---------------------------------------------------------------------------
# skill
# ---------------------------------------------------------------------------

skill_app = typer.Typer(name="skill", help="Skill system (SKILL.md open standard).")
app.add_typer(skill_app)


@skill_app.command("list")
def skill_list() -> None:
    """Print the list of loadable skills (L1 metadata)."""
    from maglab.core.skills import SkillLoader

    loader = SkillLoader()
    metas = loader.list_meta()
    if not metas:
        console.print("[dim]No skills found.[/]")
        return

    table = Table(title="MagLab Skill Catalog", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    for m in metas:
        table.add_row(m.name, m.description[:80])
    console.print(table)

    if loader.errors:
        console.print(f"[yellow]{len(loader.errors)} load error(s):[/]")
        for k, v in loader.errors.items():
            console.print(f"  [dim]{k}:[/] {v}")


# ---------------------------------------------------------------------------
# cost
# ---------------------------------------------------------------------------


@app.command("cost")
def cost_cmd() -> None:
    """Print LLM and tool costs for the current session and runs."""
    from maglab.core.budget import BudgetTracker

    tracker = BudgetTracker()
    summary = tracker.session_summary()
    table = Table(title="Session Cost Summary", show_lines=False)
    table.add_column("Item", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Session ID", tracker.session_id)
    table.add_row("LLM calls", str(summary.llm_calls))
    table.add_row("Tool calls", str(summary.tool_calls))
    table.add_row("Input tokens", str(summary.input_tokens))
    table.add_row("Output tokens", str(summary.output_tokens))
    table.add_row("Estimated cost (USD)", f"${summary.usd_cost:.4f}")
    console.print(table)


# ---------------------------------------------------------------------------
# mcp
# ---------------------------------------------------------------------------

mcp_app = typer.Typer(name="mcp", help="MCP server registry & server startup (§5.18).")
app.add_typer(mcp_app)


@mcp_app.command("list")
def mcp_list() -> None:
    """Print the list of registered MCP servers."""
    import json
    from pathlib import Path

    reg_paths = [
        Path(".maglab") / "mcp.json",
        Path.home() / ".config" / "maglab" / "mcp.json",
    ]
    found = False
    for rp in reg_paths:
        if rp.is_file():
            found = True
            try:
                data = json.loads(rp.read_text())
                servers = data.get("servers", {})
                if not servers:
                    console.print(f"[dim]{rp}: no servers registered[/]")
                    continue
                table = Table(title=f"MCP Servers ({rp})", show_lines=False)
                table.add_column("Name", style="cyan")
                table.add_column("Type")
                table.add_column("Enabled")
                for name, cfg in servers.items():
                    table.add_row(name, cfg.get("type", "stdio"), str(cfg.get("enabled", True)))
                console.print(table)
            except Exception as exc:
                console.print(f"[red]Failed to read registry ({rp}):[/] {exc}")
    if not found:
        console.print("[dim]No MCP servers registered. (create .maglab/mcp.json)[/]")


@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option("stdio", "--transport", help="Transport mode (stdio·http)."),
    host: str = typer.Option("127.0.0.1", "--host", help="HTTP bind address."),
    port: int = typer.Option(8765, "--port", help="HTTP port."),
) -> None:
    """Start the MagLab MCP server."""
    from maglab.mcp_server import create_server

    server = create_server()
    console.print(f"[cyan]MagLab MCP server starting[/] — transport={transport}")
    if transport == "http":
        server.run(transport="http", host=host, port=port)
    else:
        server.run(transport="stdio")


@mcp_app.command("add")
def mcp_add(
    name: str = typer.Argument(..., help="Registry name (used as the tool namespace prefix)."),
    command_or_url: str = typer.Argument(
        ..., help="Command string (stdio) or HTTP URL (http transport)."
    ),
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport mode: stdio (local subprocess) or http (remote SSE).",
    ),
    trust_level: str = typer.Option(
        "restricted",
        "--trust-level",
        "-T",
        help="Trust level: trusted · restricted · untrusted.",
    ),
    always_load: bool = typer.Option(
        False,
        "--always-load/--lazy",
        help="Connect to the server at startup (always_load=True) or lazily on first use.",
    ),
) -> None:
    """Register an external MCP server in the registry (§5.18).

    Example::

        maglab mcp add arxiv "npx -y @modelcontextprotocol/server-arxiv" --trust-level trusted
        maglab mcp add my-db "https://db.example.com/mcp" --transport http
    """
    from maglab.llm.mcp_client import MCPClientRegistry

    registry = MCPClientRegistry()
    registry.load()

    try:
        cfg = registry.add_server(
            name=name,
            command_or_url=command_or_url,
            transport=transport,
            trust_level=trust_level,
            always_load=always_load,
        )
    except ValueError as exc:
        console.print(f"[red]Registration failed:[/] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        f"[green]✓[/] Server registered — name=[bold]{cfg.name}[/]  "
        f"transport={cfg.transport}  trust={cfg.trust_level}  "
        f"always_load={cfg.always_load}"
    )
    console.print(f"  Registry: [dim]{registry.registry_path}[/]")


@mcp_app.command("enable")
def mcp_enable(
    name: str = typer.Argument(..., help="Registry name of the server to enable."),
) -> None:
    """Enable a previously disabled external MCP server (§5.18)."""
    from maglab.llm.mcp_client import MCPClientRegistry

    registry = MCPClientRegistry()
    registry.load()

    try:
        registry.enable_server(name)
    except KeyError as exc:
        console.print(f"[red]Server not found:[/] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[green]✓[/] Server [bold]{name}[/] enabled.")
    console.print(f"  Registry: [dim]{registry.registry_path}[/]")


@mcp_app.command("disable")
def mcp_disable(
    name: str = typer.Argument(..., help="Registry name of the server to disable."),
) -> None:
    """Disable an external MCP server without removing it from the registry (§5.18)."""
    from maglab.llm.mcp_client import MCPClientRegistry

    registry = MCPClientRegistry()
    registry.load()

    try:
        registry.disable_server(name)
    except KeyError as exc:
        console.print(f"[red]Server not found:[/] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[yellow]○[/] Server [bold]{name}[/] disabled.")
    console.print(f"  Registry: [dim]{registry.registry_path}[/]")


# ---------------------------------------------------------------------------
# agents
# ---------------------------------------------------------------------------

agents_app = typer.Typer(name="agents", help="Subagent definitions (§5.16).")
app.add_typer(agents_app)


@agents_app.command("list")
def agents_list() -> None:
    """Print the list of registered subagents."""
    from maglab.core.subagents import load_subagent_defs

    defs = load_subagent_defs()
    if not defs:
        console.print("[dim]No subagents registered.[/]")
        return

    table = Table(title="Subagent List", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Model")
    table.add_column("max_turns", justify="right")
    table.add_column("Description")
    for name, defn in defs.items():
        table.add_row(name, defn.model, str(defn.max_turns), defn.description[:60])
    console.print(table)


@agents_app.command("show")
def agents_show(
    name: str = typer.Argument(..., help="Subagent name."),
) -> None:
    """Print detailed information about a subagent."""
    from maglab.core.subagents import load_subagent_defs

    defs = load_subagent_defs()
    if name not in defs:
        console.print(f"[red]Subagent not found:[/] {name!r}")
        console.print(f"Available: {', '.join(defs.keys())}")
        raise typer.Exit(1)

    defn = defs[name]
    console.print(f"[bold cyan]{defn.name}[/]")
    console.print(f"Description: {defn.description}")
    console.print(f"Model: {defn.model}  max_turns: {defn.max_turns}")
    console.print(f"Tools: {defn.tools or '(none)'}")
    console.print(f"Context: {defn.context}")
    if defn.system_prompt:
        console.print("\n[dim]--- System prompt ---[/]")
        console.print(f"[dim]{defn.system_prompt[:500]}[/]")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

config_app = typer.Typer(
    name="config",
    help="Configuration inspection and rollback.",
    invoke_without_command=True,
)
app.add_typer(config_app)


@config_app.callback(invoke_without_command=True)
def config_cmd(ctx: typer.Context) -> None:
    """Print the current configuration."""
    if ctx.invoked_subcommand is not None:
        return
    config = load_config()
    console.print_json(config.model_dump_json(indent=2))


@config_app.command("show")
def config_show() -> None:
    """Print the current configuration."""
    config = load_config()
    console.print_json(config.model_dump_json(indent=2))


@config_app.command("path")
def config_path_cmd() -> None:
    """Print config and backup paths."""
    from maglab.config import config_backup_path, config_path

    path = config_path()
    console.print(f"config: [bold]{path}[/]")
    console.print(f"backup: [bold]{config_backup_path(path)}[/]")


@config_app.command("restore")
def config_restore_cmd() -> None:
    """Restore the previous config backup."""
    from maglab.config import restore_config

    try:
        path = restore_config()
    except FileNotFoundError as exc:
        console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/] Restored previous MagLab config: [bold]{path}[/]")


@config_app.command("reset")
def config_reset_cmd() -> None:
    """Reset config to defaults, keeping the previous file as .bak."""
    from maglab.config import reset_config

    path = reset_config()
    console.print(f"[green]✓[/] Reset MagLab config to defaults: [bold]{path}[/]")


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@app.command("setup")
def setup_cmd(
    feature: str = typer.Argument(
        "all",
        help="Feature to set up: all·llm·literature·simulation·figure·instrument·authoring·review·gateway·mcp.",
    ),
) -> None:
    """Show terminal setup guidance for MagLab research features."""
    from maglab.setup import render_setup

    render_setup(feature, console=console)


# ---------------------------------------------------------------------------
# install / workspace
# ---------------------------------------------------------------------------


@app.command("install")
def install_cmd() -> None:
    """Print global installation commands."""
    from rich.markup import escape

    from maglab.setup import PIPX_INSTALL, RECOMMENDED_INSTALL, UV_TOOL_INSTALL

    console.print("[bold]Global MagLab install[/]")
    console.print(f"  Recommended: [cyan]{escape(RECOMMENDED_INSTALL)}[/]")
    console.print(f"  uv tool:     [cyan]{escape(UV_TOOL_INSTALL)}[/]")
    console.print(f"  pipx:        [cyan]{escape(PIPX_INSTALL)}[/]")
    console.print()
    console.print(
        "After installation, open any research folder and run [bold]maglab[/]. "
        "MagLab will use that folder as the workspace while keeping config/data/cache in global app paths."
    )


workspace_app = typer.Typer(
    name="workspace",
    help="Current-folder workspace status and initialization.",
    invoke_without_command=True,
)
app.add_typer(workspace_app)


@workspace_app.callback(invoke_without_command=True)
def workspace_callback(ctx: typer.Context) -> None:
    """Show workspace status by default."""
    if ctx.invoked_subcommand is not None:
        return
    workspace_status()


@workspace_app.command("status")
def workspace_status() -> None:
    """Show the active workspace and global MagLab paths."""
    from maglab.workspace import workspace_info

    info = workspace_info()
    table = Table(title="MagLab workspace")
    table.add_column("Scope", style="cyan")
    table.add_column("Path")
    table.add_row("workspace root", str(info.root))
    table.add_row("project state", str(info.local_state_dir))
    table.add_row("MAGLAB.md", str(info.maglab_md or "(not found)"))
    table.add_row("global config", str(info.config_dir))
    table.add_row("global data", str(info.data_dir))
    table.add_row("global cache", str(info.cache_dir))
    console.print(table)


@workspace_app.command("init")
def workspace_init() -> None:
    """Create a local MAGLAB.md marker in the current folder."""
    from maglab.workspace import init_workspace

    marker, created = init_workspace()
    if created:
        console.print(f"[green]✓[/] Created workspace marker: [bold]{marker}[/]")
    else:
        console.print(f"[dim]Workspace marker already exists:[/] {marker}")


@workspace_app.command("tree")
def workspace_tree(
    max_entries: int = typer.Option(80, "--max", "-n", help="Maximum entries to display."),
) -> None:
    """Show the files MagLab can see from the current folder."""
    from maglab.workspace import iter_workspace_entries, workspace_root

    root = workspace_root()
    console.print(f"[bold]Workspace:[/] {root}")
    entries = iter_workspace_entries(root, max_entries=max_entries)
    if not entries:
        console.print("[dim]No visible files.[/]")
        return
    for entry in entries:
        console.print(f"  {entry}")


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@app.command("version")
def version() -> None:
    """Print the version."""
    console.print(f"maglab {__version__}")


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


@app.command("info")
def info() -> None:
    """Print installation and runtime environment information."""
    console.print(f"maglab {__version__}  ·  Python {sys.version.split()[0]}  ·  {sys.platform}")


# ===========================================================================
# P1 commands — sim
# ===========================================================================

sim_app = typer.Typer(
    name="sim",
    help="[P1] Multiscale simulation (doctor·micro·validate·plot·job).",
    no_args_is_help=True,
)
app.add_typer(sim_app)


def _print_sim_check_table(title: str, rows: list[dict[str, Any]]) -> None:
    """Render a compact simulation environment check table."""
    table = Table(title=title, show_lines=False)
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_column("Action")
    for row in rows:
        ok = bool(row.get("ok"))
        table.add_row(
            str(row.get("name", "")),
            "[green]ready[/]" if ok else "[yellow]missing[/]",
            str(row.get("detail", "")),
            str(row.get("action", "")),
        )
    console.print(table)


@sim_app.command("doctor")
def sim_doctor(
    backend: str = typer.Option(
        "auto",
        "--backend",
        "-b",
        help="Target path to diagnose (auto·cpu·local-gpu·ssh-gpu·ssh-hpc·mock).",
    ),
    host: str | None = typer.Option(None, "--host", help="SSH host for remote GPU/HPC checks."),
    user: str | None = typer.Option(None, "--user", "-u", help="SSH username."),
    remote_work_dir: str = typer.Option(
        "/tmp/maglab", "--remote-work-dir", help="Remote working directory."
    ),
    probe_ssh: bool = typer.Option(
        False,
        "--probe-ssh/--no-probe-ssh",
        help="Actually test non-interactive SSH connectivity.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Diagnose simulation readiness for CPU, local GPU, SSH GPU, and SSH HPC paths."""
    import json

    from maglab.sim.environment import diagnose_sim_environment

    report = diagnose_sim_environment(
        backend=backend,
        host=host,
        user=user,
        remote_work_dir=remote_work_dir,
        probe_ssh=probe_ssh,
    )
    if json_output:
        typer.echo(json.dumps(report, indent=2))
        return

    console.print(
        "[bold cyan]Simulation environment[/] "
        f"requested={report['backend_requested']}  recommended={report['recommended_backend']}"
    )
    cpu_engines = report.get("cpu_engines", [])
    console.print(f"  CPU engines: {', '.join(cpu_engines) if cpu_engines else 'none detected'}")
    console.print(
        "  Local GPU: "
        + ("[green]ready[/]" if report.get("local_gpu_ready") else "[yellow]not ready[/]")
    )
    if report.get("ssh_target"):
        console.print(f"  SSH target: {report['ssh_target']}")

    _print_sim_check_table("Python simulation packages", report["python"])
    _print_sim_check_table("External solver and remote-execution tools", report["binaries"])
    if report["ssh"]:
        _print_sim_check_table("SSH target", report["ssh"])

    console.print("[bold]Next commands[/]")
    for item in report["recommendations"]:
        console.print(f"  • {item}")


@sim_app.command("micro")
def sim_micro(
    material: str = typer.Option(
        "Permalloy", "--material", "-m", help="Material ID (e.g. Permalloy)."
    ),
    nx: int = typer.Option(64, "--nx", help="Number of cells in x direction."),
    ny: int = typer.Option(64, "--ny", help="Number of cells in y direction."),
    nz: int = typer.Option(1, "--nz", help="Number of cells in z direction."),
    cell_nm: float = typer.Option(4.0, "--cell-nm", help="Cell size [nm]."),
    engine: str = typer.Option(
        "auto", "--engine", "-e", help="Solver engine (auto·magnumnp·oommf·mumax3)."
    ),
    t_ns: float = typer.Option(
        0.0, "--t-ns", help="Simulation time [ns]. 0 means static relaxation."
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path stem."),
) -> None:
    """Run a micromagnetic simulation.

    Exits with a warning if external solvers (MuMax3·OOMMF·magnum.np) are not installed.
    """
    from maglab.physics.materials import lookup
    from maglab.sim.spec import (
        MicroMagGeometry,
        MicroMagMaterial,
        MultiScaleSpec,
        ScaleSpec,
        ScaleType,
    )
    from maglab.sim.validate import validate

    mat_data = lookup(material)
    if mat_data is None:
        console.print(f"[red]Material not found:[/] {material!r}")
        raise typer.Exit(1)

    mag_mat = MicroMagMaterial(
        Ms_Am=float(mat_data.Ms_Am) if mat_data.Ms_Am is not None else 800000.0,
        A_Jm=float(mat_data.A_Jm) if mat_data.A_Jm is not None else 1.3e-11,
        alpha=float(mat_data.alpha) if mat_data.alpha and mat_data.alpha > 0 else 0.01,
        K_Jm3=float(mat_data.K_Jm3) if mat_data.K_Jm3 is not None else 0.0,
    )
    geom = MicroMagGeometry(nx=nx, ny=ny, nz=nz, dx_nm=cell_nm, dy_nm=cell_nm, dz_nm=cell_nm)
    scale_spec = ScaleSpec(
        scale=ScaleType.micro,
        engine=engine,
        material=mag_mat,
        geometry=geom,
        t_sim_ns=t_ns,
    )
    multi = MultiScaleSpec(name=f"{material}_micro", scales=[scale_spec])

    # Static validation
    try:
        validate(multi)
        console.print("[green]✓[/] SimSpec static validation passed.")
    except Exception as exc:
        console.print(f"[red]✗ Validation failed:[/] {exc}")
        raise typer.Exit(1) from exc

    console.print("[dim]sim micro → backend execution — warns if solver not installed[/]")
    console.print(
        f"[cyan]SimSpec:[/] {material} | grid={nx}×{ny}×{nz} | cell={cell_nm}nm | engine={engine}"
    )


@sim_app.command("validate")
def sim_validate(
    spec_json: str = typer.Argument(..., help="MultiScaleSpec JSON string or file path."),
) -> None:
    """Statically validate a MultiScaleSpec."""
    import json
    from pathlib import Path

    from maglab.sim.spec import MultiScaleSpec
    from maglab.sim.validate import validate

    # Parse JSON
    raw = spec_json.strip()
    if Path(raw).is_file():
        raw = Path(raw).read_text(encoding="utf-8")

    try:
        data = json.loads(raw)
        spec = MultiScaleSpec.model_validate(data)
    except Exception as exc:
        console.print(f"[red]JSON parse failed:[/] {exc}")
        raise typer.Exit(1) from exc

    try:
        validate(spec)
        console.print(f"[green]✓[/] Validation passed — {spec.name}")
    except Exception as exc:
        console.print(f"[red]✗ Validation failed:[/] {exc}")
        raise typer.Exit(1) from exc


@sim_app.command("plot")
def sim_plot(
    data_file: str = typer.Argument(..., help="Experimental data CSV file path."),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path (.pdf/.svg/.eps)."
    ),
    fmt: str = typer.Option("pdf", "--format", "-f", help="Export format (pdf·svg·eps)."),
    journal: str = typer.Option(
        "nature", "--journal", "-j", help="Journal target (nature·aps·ieee·elsevier)."
    ),
    caption: str = typer.Option("", "--caption", help="Figure caption."),
) -> None:
    """F6: experimental data CSV → auto-inference → FigureSpec → vector figure output."""

    from maglab.figure.spec import ColumnWidth, JournalTarget
    from maglab.sim.plot import plot_data_to_figure

    # Parse journal
    try:
        j = JournalTarget(journal)
    except ValueError:
        console.print(f"[red]Unknown journal:[/] {journal!r}. Available: nature·aps·ieee·elsevier")
        raise typer.Exit(1) from None

    with console.status("[dim]Loading data and rendering figure…[/]"):
        try:
            saved_path, spec, ledger = plot_data_to_figure(
                data_path=data_file,
                output_path=output,
                journal=j,
                column_width=ColumnWidth.SINGLE,
                fmt=fmt,  # type: ignore[arg-type]
                caption=caption,
            )
        except FileNotFoundError as exc:
            console.print(f"[red]File not found:[/] {exc}")
            raise typer.Exit(1) from exc
        except Exception as exc:
            console.print(f"[red]Figure generation failed:[/] {exc}")
            raise typer.Exit(1) from exc

    console.print(f"[green]✓[/] Figure saved: [bold]{saved_path}[/]")
    n_dp = len(ledger)
    console.print(f"  {n_dp} DataPoint(s) bound | plot kind: {spec.panels[0].plot_kind}")
    if spec.caption:
        console.print(f"  Caption: [dim]{spec.caption[:120]}[/]")


@sim_app.command("job")
def sim_job(
    job_id: str | None = typer.Argument(None, help="Job ID (omit for full list)."),
) -> None:
    """Query simulation job status.

    Currently P1 supports only in-memory jobs (HPC job tracking will be added in P3).
    """
    if job_id:
        console.print(f"[dim]Job {job_id!r} status: supported in P3 HPC job tracking.[/]")
    else:
        console.print("[dim]No jobs currently running. (HPC job tracking added in P3)[/]")


# ---------------------------------------------------------------------------
# [P3] sim dft — DFT input generation + output parsing
# ---------------------------------------------------------------------------


@sim_app.command("dft")
def sim_dft(
    structure: str = typer.Option(
        "bcc_fe", "--structure", "-s", help="Structure ID (e.g. bcc_fe)."
    ),
    engine: str = typer.Option("qe", "--engine", "-e", help="DFT engine (vasp·qe·fleur)."),
    calc_type: str = typer.Option(
        "scf", "--calc-type", "-c", help="Calculation type (scf·jij·mae·dmi)."
    ),
    output_dir: str = typer.Option(
        "./dft_run", "--output-dir", "-o", help="Input file output directory."
    ),
    mock: bool = typer.Option(True, "--mock/--real", help="Mock mode (default: True)."),
) -> None:
    """[P3] Generate DFT input files and parse results.

    Operates in mock mode if external solvers (VASP·QE·FLEUR) are not installed.
    """
    from pathlib import Path

    from maglab.sim.dft.input_gen import DFTCalcType, DFTEngine, DFTInputGenerator

    # Parse engine
    try:
        dft_engine = DFTEngine(engine.lower())
    except ValueError:
        console.print(f"[red]Unknown DFT engine:[/] {engine!r}. Supported: vasp·qe·fleur")
        raise typer.Exit(1) from None

    # Parse calc_type
    try:
        dft_calc_type = DFTCalcType(calc_type.lower())
    except ValueError:
        console.print(f"[red]Unknown calc_type:[/] {calc_type!r}. Supported: scf·jij·mae·dmi")
        raise typer.Exit(1) from None

    out_path = Path(output_dir)
    params = {"calc_type": dft_calc_type}

    console.print(
        f"[cyan]DFT input generation:[/] engine={engine} | calc_type={calc_type} | structure={structure}"
    )

    with console.status("[dim]Generating DFT input files…[/]"):
        gen = DFTInputGenerator(engine=dft_engine)
        try:
            files = gen.generate(
                structure=structure,  # type: ignore[arg-type]
                params=params,
                output_dir=out_path,
            )
        except Exception as exc:
            console.print(f"[red]Input generation failed:[/] {exc}")
            raise typer.Exit(1) from exc

    console.print(f"[green]✓[/] DFT input files generated → {out_path}")
    for name, path in files.items():
        console.print(f"  [dim]{name}:[/] {path}")

    if mock:
        console.print(
            "[yellow]Mock mode:[/] solver not executed. "
            "Use --real mode after solver completes to parse results."
        )


# ---------------------------------------------------------------------------
# [P3] sim atomistic — atomistic input generation + result parsing
# ---------------------------------------------------------------------------


@sim_app.command("atomistic")
def sim_atomistic(
    engine: str = typer.Option(
        "vampire", "--engine", "-e", help="Atomistic engine (vampire·spirit)."
    ),
    j_ij_k: float = typer.Option(
        398.0, "--j-ij-k", help="1NN exchange coupling constant [K] (default: bcc Fe Pajda 2001)."
    ),
    t_max_k: float = typer.Option(1300.0, "--t-max-k", help="Maximum temperature [K]."),
    output_dir: str = typer.Option(
        "./atomistic_run", "--output-dir", "-o", help="Output directory."
    ),
    mock: bool = typer.Option(True, "--mock/--real", help="Mock mode (default: True)."),
) -> None:
    """[P3] Generate atomistic simulation input files and parse results.

    Operates in mock mode if external solvers (VAMPIRE·Spirit) are not installed.
    Default parameters: bcc Fe (Pajda 2001, Phys. Rev. B 64, 174402).
    """
    from pathlib import Path

    from maglab.sim.atomistic.input_gen import AtomisticEngine, AtomisticInputGenerator
    from maglab.sim.atomistic.parse_atomistic import parse_vampire_output

    try:
        atm_engine = AtomisticEngine(engine.lower())
    except ValueError:
        console.print(f"[red]Unknown atomistic engine:[/] {engine!r}. Supported: vampire·spirit")
        raise typer.Exit(1) from None

    out_path = Path(output_dir)
    params = {"J_ij_K": j_ij_k, "T_max_K": t_max_k}

    console.print(
        f"[cyan]Atomistic simulation:[/] engine={engine} | J_ij={j_ij_k:.1f} K | T_max={t_max_k:.0f} K"
    )

    with console.status("[dim]Generating atomistic input files…[/]"):
        gen = AtomisticInputGenerator(engine=atm_engine)
        try:
            files = gen.generate(params=params, output_dir=out_path)
        except Exception as exc:
            console.print(f"[red]Input generation failed:[/] {exc}")
            raise typer.Exit(1) from exc

    console.print(f"[green]✓[/] Atomistic input files generated → {out_path}")
    for name, path in files.items():
        console.print(f"  [dim]{name}:[/] {path}")

    if mock:
        console.print(
            "[yellow]Mock mode:[/] solver not executed. "
            "Use --real mode after actual run to parse results."
        )
    else:
        # Real mode: attempt to parse output
        with console.status("[dim]Parsing atomistic results…[/]"):
            try:
                result = parse_vampire_output(out_path)
                console.print("[green]✓[/] Atomistic results parsed")
                if result.T_C_K:
                    console.print(f"  [bold]T_C[/] = {result.T_C_K:.1f} K")
                if result.M_s_Am:
                    console.print(f"  [bold]M_s(0)[/] = {result.M_s_Am:.3e} A/m")
            except Exception as exc:
                console.print(f"[yellow]Result parsing failed:[/] {exc}")


# ---------------------------------------------------------------------------
# [P3] sim pipeline — full multiscale pipeline
# ---------------------------------------------------------------------------


@sim_app.command("pipeline")
def sim_pipeline(
    structure: str = typer.Option("bcc_fe", "--structure", "-s", help="Structure ID."),
    scales: str = typer.Option(
        "dft,atomistic,micro,device",
        "--scales",
        help="Comma-separated list of scales to run.",
    ),
    target_temp_k: float = typer.Option(300.0, "--target-temp", help="Target temperature [K]."),
    dft_engine: str = typer.Option("qe", "--dft-engine", help="DFT engine."),
    atomistic_engine: str = typer.Option("vampire", "--atomistic-engine", help="Atomistic engine."),
    backend: str = typer.Option(
        "mock", "--backend", "-b", help="Execution backend (mock·hpc·gpu)."
    ),
    work_dir: str = typer.Option("./pipeline_run", "--work-dir", "-w", help="Working directory."),
) -> None:
    """[P3] Run the DFT → atomistic → micromagnetic → device multiscale pipeline.

    Each scale's output is automatically converted to the next scale's input (Appendix D unit continuity).
    Mock mode: uses bcc Fe golden values (Pajda 2001, Phys. Rev. B 64, 174402).
    """
    from pathlib import Path

    from maglab.sim.pipeline import run_pipeline

    scale_list = [s.strip() for s in scales.split(",") if s.strip()]

    console.print(
        f"[cyan]Multiscale pipeline:[/] structure={structure} | "
        f"scales={' → '.join(scale_list)} | backend={backend}"
    )

    with console.status("[dim]Running pipeline…[/]"):
        try:
            result = run_pipeline(
                structure=structure,  # type: ignore[arg-type]
                scales=scale_list,
                target_temp_K=target_temp_k,
                dft_engine=dft_engine,
                atomistic_engine=atomistic_engine,
                backend=backend,
                work_dir=Path(work_dir),
            )
        except Exception as exc:
            console.print(f"[red]Pipeline failed:[/] {exc}")
            raise typer.Exit(1) from exc

    console.print(f"[green]✓[/] {result.summary()}")

    # Print key results
    if result.atomistic_result and result.atomistic_result.T_C_K:
        console.print(f"  [bold]T_C[/] = {result.atomistic_result.T_C_K:.1f} K")
    if result.micro_params:
        a_jm = result.micro_params.get("A_Jm_at_T")
        ms_am = result.micro_params.get("Ms_Am_at_T")
        if a_jm:
            console.print(f"  [bold]A(T={target_temp_k:.0f}K)[/] = {a_jm:.3e} J/m")
        if ms_am:
            console.print(f"  [bold]Ms(T={target_temp_k:.0f}K)[/] = {ms_am:.3e} A/m")

    if result.errors:
        for err in result.errors:
            console.print(f"  [red]Error:[/] {err}")
    if result.warnings:
        for warn in result.warnings:
            console.print(f"  [yellow]Warning:[/] {warn}")

    console.print(f"  [dim]{len(result.provenance_chain)} provenance DataPoint(s) recorded[/]")


# ===========================================================================
# P1 commands — figure
# ===========================================================================

figure_app = typer.Typer(
    name="figure",
    help="[P1] Figure production engine (spec·render·compose·export).",
    no_args_is_help=True,
)
app.add_typer(figure_app)


# ---------------------------------------------------------------------------
# figure primitives — catalog sub-app
# ---------------------------------------------------------------------------

primitives_app = typer.Typer(
    name="primitives",
    help="Figure primitive catalog (list · show).",
    no_args_is_help=True,
)
figure_app.add_typer(primitives_app)


@primitives_app.command("list")
def figure_primitives_list(
    search: str | None = typer.Option(None, "--search", help="Filter primitives by keyword."),
) -> None:
    """List catalog primitives (name, category, description)."""
    from maglab.figure.primitives.registry import make_default_registry

    reg = make_default_registry()
    entries = reg.search(search) if search else reg.list_all()
    if not entries:
        console.print("[dim]No primitives found.[/]")
        return
    table = Table(title=f"Primitive catalog ({len(entries)})", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Category")
    table.add_column("Description")
    for entry in sorted(entries, key=lambda e: str(e.get("name", ""))):
        table.add_row(
            str(entry.get("name", "")),
            str(entry.get("category", "")),
            str(entry.get("description", "")),
        )
    console.print(table)


@primitives_app.command("show")
def figure_primitives_show(
    name: str = typer.Argument(..., help="Primitive name."),
) -> None:
    """Show a catalog primitive's metadata."""
    from maglab.figure.primitives.registry import make_default_registry

    reg = make_default_registry()
    index = {str(e.get("name", "")): e for e in reg.list_all()}
    meta = index.get(name)
    if meta is None:
        console.print(f"[red]Primitive not found:[/] {name!r}")
        console.print(f"Available: {', '.join(sorted(index))}")
        raise typer.Exit(1)
    table = Table(title=f"Primitive: {name}", show_lines=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Category", str(meta.get("category", "")))
    table.add_row("Tags", ", ".join(meta.get("tags", [])))
    table.add_row("Description", str(meta.get("description", "")))
    table.add_row("Journal styles", ", ".join(meta.get("journal_styles", [])))
    console.print(table)


@figure_app.command("spec")
def figure_spec_cmd(
    output: str = typer.Option(
        "figure_spec.json", "--output", "-o", help="FigureSpec JSON output path."
    ),
    journal: str = typer.Option("nature", "--journal", "-j", help="Journal target."),
    kind: str = typer.Option(
        "xy", "--kind", "-k", help="Plot kind (hysteresis·hall·fmr·dispersion·xy)."
    ),
) -> None:
    """Write and output a skeleton FigureSpec JSON."""
    from pathlib import Path

    from maglab.figure.spec import (
        AxisSpec,
        ColumnWidth,
        FigureSpec,
        GridLayout,
        GridPosition,
        JournalTarget,
        PanelSpec,
        PanelType,
        PlotKind,
    )

    try:
        j = JournalTarget(journal)
    except ValueError:
        console.print(f"[red]Unknown journal:[/] {journal!r}")
        raise typer.Exit(1) from None

    try:
        pk = PlotKind(kind)
    except ValueError:
        console.print(
            f"[red]Unknown plot kind:[/] {kind!r}. Available: hysteresis·hall·fmr·dispersion·xy"
        )
        raise typer.Exit(1) from None

    # Skeleton spec — data_point_ids must be filled in by the user (dummy UUID included)
    import uuid as _uuid

    dummy_dp_id = str(_uuid.uuid4())
    spec = FigureSpec(
        figure_id=str(_uuid.uuid4()),
        journal=j,
        column_width=ColumnWidth.SINGLE,
        panels=[
            PanelSpec(
                panel_id="p1",
                panel_type=PanelType.DATA_PLOT,
                plot_kind=pk,
                data_point_ids=[dummy_dp_id],
                grid_position=GridPosition(row=0, col=0),
                x_axis=AxisSpec(label="x (units)"),
                y_axis=AxisSpec(label="y (units)"),
            )
        ],
        layout=GridLayout(nrows=1, ncols=1),
        caption=f"Figure spec skeleton — {j.value} journal | plot kind: {pk.value}.",
    )

    out = Path(output)
    out.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]✓[/] FigureSpec skeleton written: [bold]{out}[/]")
    console.print(
        f"  Replace the dummy UUID ({dummy_dp_id!r}) in data_point_ids with a real DataPoint ID."
    )


@figure_app.command("render")
def figure_render_cmd(
    spec_path: str = typer.Argument(..., help="FigureSpec JSON file path."),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("pdf", "--format", "-f", help="Export format (pdf·svg·eps)."),
    datapoints_json: str | None = typer.Option(
        None,
        "--datapoints",
        "-d",
        help="DataPoint JSON file path (ID → DataPoint dictionary).",
    ),
) -> None:
    """Read a FigureSpec JSON and render a vector figure."""
    import json
    from pathlib import Path

    from maglab.figure.compose import FigureComposer
    from maglab.figure.export import FigureExporter
    from maglab.figure.spec import FigureSpec
    from maglab.provenance.datapoint import DataPoint

    # Parse FigureSpec
    try:
        spec = FigureSpec.model_validate_json(Path(spec_path).read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]FigureSpec parse failed:[/] {exc}")
        raise typer.Exit(1) from exc

    # Load DataPoint ledger
    ledger: dict[str, DataPoint] = {}
    if datapoints_json:
        try:
            raw = json.loads(Path(datapoints_json).read_text(encoding="utf-8"))
            for dp_id, dp_dict in raw.items():
                ledger[dp_id] = DataPoint.model_validate(dp_dict)
        except Exception as exc:
            console.print(f"[red]DataPoint JSON parse failed:[/] {exc}")
            raise typer.Exit(1) from exc

    # Output path
    out_path = Path(output) if output else Path(spec_path).with_suffix(f".{fmt}")

    with console.status("[dim]Rendering figure…[/]"):
        import contextlib

        import matplotlib.pyplot as plt

        try:
            composer = FigureComposer()
            exporter = FigureExporter()
            fig = composer.compose(spec, ledger)
            saved = exporter.export(fig, out_path, fmt=fmt)  # type: ignore[arg-type]
        except Exception as exc:
            console.print(f"[red]Render failed:[/] {exc}")
            raise typer.Exit(1) from exc
        finally:
            with contextlib.suppress(Exception):
                plt.close(fig)

    console.print(f"[green]✓[/] Figure saved: [bold]{saved}[/]")


@figure_app.command("compose")
def figure_compose_cmd(
    spec_path: str = typer.Argument(..., help="FigureSpec JSON file path."),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("pdf", "--format", "-f", help="Export format (pdf·svg·eps)."),
) -> None:
    """Compose a FigureSpec into a multi-panel figure (same as render, compose stage explicit)."""
    from pathlib import Path

    from maglab.figure.compose import FigureComposer
    from maglab.figure.export import FigureExporter
    from maglab.figure.spec import FigureSpec

    try:
        spec = FigureSpec.model_validate_json(Path(spec_path).read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]FigureSpec parse failed:[/] {exc}")
        raise typer.Exit(1) from exc

    out_path = Path(output) if output else Path(spec_path).with_suffix(f".{fmt}")

    with console.status("[dim]Composing multi-panel figure…[/]"):
        import contextlib

        import matplotlib.pyplot as plt

        try:
            fig = FigureComposer().compose(spec, {})
            saved = FigureExporter().export(fig, out_path, fmt=fmt)  # type: ignore[arg-type]
        except Exception as exc:
            console.print(f"[red]Composition failed:[/] {exc}")
            raise typer.Exit(1) from exc
        finally:
            with contextlib.suppress(Exception):
                plt.close(fig)

    console.print(f"[green]✓[/] Multi-panel figure saved: [bold]{saved}[/]")
    console.print(f"  Panels: {len(spec.panels)} | Journal: {spec.journal.value}")


@figure_app.command("export")
def figure_export_cmd(
    spec_path: str = typer.Argument(..., help="FigureSpec JSON file path."),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file stem (no extension)."
    ),
    formats: list[str] | None = typer.Option(  # noqa: B008
        None, "--format", "-f", help="Export format list (default: pdf,svg)."
    ),
) -> None:
    """Export a vector figure to multiple formats."""
    from pathlib import Path

    from maglab.figure.compose import FigureComposer
    from maglab.figure.export import FigureExporter
    from maglab.figure.spec import FigureSpec

    try:
        spec = FigureSpec.model_validate_json(Path(spec_path).read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]FigureSpec parse failed:[/] {exc}")
        raise typer.Exit(1) from exc

    stem = Path(output) if output else Path(spec_path).with_suffix("")
    fmt_list = list(formats) if formats else ["pdf", "svg"]

    with console.status("[dim]Exporting figure…[/]"):
        import contextlib

        import matplotlib.pyplot as plt

        try:
            fig = FigureComposer().compose(spec, {})
            results = FigureExporter().export_all(
                fig,
                stem,
                formats=fmt_list,  # type: ignore[arg-type]
            )
        except Exception as exc:
            console.print(f"[red]Export failed:[/] {exc}")
            raise typer.Exit(1) from exc
        finally:
            with contextlib.suppress(Exception):
                plt.close(fig)

    for fmt_key, path in results.items():
        console.print(f"[green]✓[/] [{fmt_key.upper()}] {path}")


# ===========================================================================
# P4 commands — instr
# ===========================================================================

instr_app = typer.Typer(
    name="instr",
    help="[P4] Instrument code generation (scaffold·scpi·script·check·ingest·implement).",
    invoke_without_command=True,
)
app.add_typer(instr_app)


@instr_app.callback()
def instr_callback(ctx: typer.Context) -> None:
    """[P4] Instrument code generation CLI."""
    if ctx.invoked_subcommand is None:
        console.print(
            "[bold cyan][P4] maglab instr[/] — instrument code generation workflow\n"
            "\n"
            "Subcommands: scaffold · scpi · script · check · ingest · implement\n"
            "Help: [bold]maglab instr --help[/]"
        )


@instr_app.command("scaffold")
def instr_scaffold(
    model: str = typer.Argument(
        ..., help="Instrument model name (★ user confirmation required — no guessing)."
    ),
    iface: str = typer.Option("GPIB", "--iface", "-i", help="Interface (GPIB·USB·TCPIP·SERIAL)."),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path."),
    gpib_addr: int = typer.Option(1, "--gpib-addr", help="GPIB address (for GPIB interface)."),
) -> None:
    """Generate a PyVISA backend skeleton Python file.

    ★ Model name must be confirmed by the user — no guessing (§13.2).
    Before executing the generated file, run `maglab instr check` to pass safety validation.
    """
    from pathlib import Path

    from maglab.instrument.scaffold import generate_scaffold

    out_path = Path(output) if output else Path(f"{model.replace(' ', '_')}_driver.py")

    with console.status(f"[dim]Generating skeleton ({model})…[/]"):
        code = generate_scaffold(
            model=model,
            iface=iface,
            output_path=out_path,
            options={"gpib_addr": gpib_addr},
        )

    console.print(
        f"[green]✓[/] Skeleton generated: [bold]{out_path}[/]  ({len(code.splitlines())} lines)"
    )
    console.print(
        f"  [yellow]★[/] Before running, pass safety validation with [bold]maglab instr check {out_path}[/]."
    )


@instr_app.command("scpi")
def instr_scpi(
    commands: list[str] = typer.Argument(..., help="SCPI command string list."),  # noqa: B008
    model: str = typer.Option("generic", "--model", "-m", help="Safety profile model key."),
) -> None:
    """Statically validate a SCPI command sequence."""
    from maglab.instrument.scpi import validate_sequence

    result = validate_sequence(list(commands))
    if result.ok:
        console.print(f"[green]✓[/] {result.summary()}")
    else:
        console.print(f"[red]✗[/] {result.summary()}")
        raise typer.Exit(1)


@instr_app.command("script")
def instr_script(
    model: str = typer.Argument(..., help="Instrument model name (★ user confirmation required)."),
    description: str = typer.Option(
        ..., "--description", "-d", help="Experiment description (natural language)."
    ),
    iface: str = typer.Option("GPIB", "--iface", "-i", help="Interface."),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path."),
    sweep_start: float = typer.Option(0.0, "--start", help="Sweep start value."),
    sweep_stop: float = typer.Option(1.0, "--stop", help="Sweep stop value."),
    sweep_step: float = typer.Option(0.1, "--step", help="Sweep step."),
    safety_model: str = typer.Option("generic", "--safety-model", help="Safety profile key."),
) -> None:
    """Generate a measurement script.

    ★ Model name must be confirmed by the user — no guessing (§13.2).
    The generated file includes safety annotations and an explicit Tier 3 execution notice.
    """
    from pathlib import Path

    from maglab.instrument.script import generate_measurement_script

    out_path = Path(output) if output else Path(f"{model.replace(' ', '_')}_measurement.py")

    with console.status(f"[dim]Generating measurement script ({model})…[/]"):
        code, safety_result = generate_measurement_script(
            model=model,
            description=description,
            iface=iface,
            output_path=None,  # save after validation
            sweep_start=sweep_start,
            sweep_stop=sweep_stop,
            sweep_step=sweep_step,
            safety_model=safety_model,
        )

    if safety_result.ok:
        out_path.write_text(code, encoding="utf-8")
        console.print(
            f"[green]✓[/] Script generated: [bold]{out_path}[/]  ({len(code.splitlines())} lines)"
        )
        console.print("  [yellow]★[/] Tier 3 execution — a human must review before running.")
        if safety_result.warnings:
            for w in safety_result.warnings:
                console.print(f"  [yellow]Warning:[/] {w.message}")
    else:
        console.print("[red]✗[/] Safety validation failed — script was not saved.")
        console.print(safety_result.summary())
        raise typer.Exit(1)


@instr_app.command("check")
def instr_check(
    path: str = typer.Argument(..., help="Script file path to validate."),
    model: str = typer.Option("generic", "--model", "-m", help="Safety profile model key."),
) -> None:
    """Statically validate the safety envelope of a script or SCPI file."""
    from pathlib import Path

    from maglab.instrument.safety import SafetyChecker, get_profile

    script_path = Path(path)
    if not script_path.is_file():
        console.print(f"[red]File not found:[/] {path}")
        raise typer.Exit(1)

    profile = get_profile(model)
    checker = SafetyChecker(profile)
    result = checker.check_file(script_path)

    if result.ok:
        console.print(f"[green]✓[/] {result.summary()}")
        if result.warnings:
            for w in result.warnings:
                console.print(f"  [yellow]Warning line {w.line_number}:[/] {w.message}")
    else:
        console.print("[red]✗[/] Safety validation failed:")
        for v in result.violations:
            if v.is_error:
                console.print(f"  [red]Error line {v.line_number}:[/] {v.message}")
        for w in result.warnings:
            console.print(f"  [yellow]Warning line {w.line_number}:[/] {w.message}")
        raise typer.Exit(1)


@instr_app.command("ingest")
def instr_ingest(
    model: str = typer.Argument(..., help="Instrument model name (★ user confirmation required)."),
    manufacturer: str = typer.Option(
        "", "--manufacturer", "-mfr", help="Manufacturer name (optional)."
    ),
    manual_path: str | None = typer.Option(
        None, "--manual-path", "-p", help="Local PDF file path (web search used if omitted)."
    ),
) -> None:
    """Collect a manual PDF and build the RAG index.

    ★ Model name must be confirmed by the user — no guessing (§13.2).
    """
    from pathlib import Path

    from maglab.instrument.manual_rag import ManualRAGPipeline
    from maglab.instrument.manual_search import search_manual

    mfr = manufacturer or None

    with console.status(f"[dim]Collecting manual ({model})…[/]"):
        if manual_path:
            search_result = search_manual(model, manufacturer=mfr, local_pdf=Path(manual_path))
        else:
            search_result = search_manual(model, manufacturer=mfr)

    if not search_result.ok:
        console.print(f"[red]✗[/] Manual collection failed: {search_result.error}")
        console.print("  [dim]Hint: specify a local PDF with --manual-path <pdf>.[/]")
        raise typer.Exit(1)

    console.print(f"[green]✓[/] Manual collected: {search_result.pdf_path}")

    if search_result.pdf_path is None:
        console.print("[red]✗[/] No PDF path available.")
        raise typer.Exit(1)

    # Build RAG index
    pipeline = ManualRAGPipeline()
    model_key = f"{(search_result.manufacturer or model).lower().replace(' ', '-')}-{model.lower().replace(' ', '-')}"

    with console.status("[dim]Building RAG index…[/]"):
        index = pipeline.ingest(model_key, search_result.pdf_path)

    console.print(f"[green]✓[/] RAG index built: {index.chunk_count} chunks → {index._db_path}")


@instr_app.command("implement")
def instr_implement(
    description: str = typer.Argument(..., help="Experiment description in natural language."),
    instruments: str = typer.Option(
        ...,
        "--instruments",
        "-i",
        help="Comma-separated model name list. ★ User confirmation required.",
    ),
    safety_model: str = typer.Option("generic", "--safety-model", help="Safety profile key."),
    output_dir: str = typer.Option("outputs", "--output-dir", "-o", help="Output directory."),
) -> None:
    """Experiment description + instrument list → implement measurement scripts (Loop B prep).

    ★ Model names must be confirmed by the user — no guessing (§13.2).
    Actual hardware execution is Tier 3 — a human must review before running.
    """
    import datetime
    from pathlib import Path

    from maglab.instrument.script import ScriptConfig, ScriptGenerator

    model_list = [m.strip() for m in instruments.split(",") if m.strip()]
    out_dir = Path(output_dir) / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    generator = ScriptGenerator()

    for model in model_list:
        config = ScriptConfig(
            model=model,
            description=description,
            safety_model=safety_model,
        )
        out_path = out_dir / f"{model.replace(' ', '_')}_script.py"

        with console.status(f"[dim]Implementing {model} script…[/]"):
            code, safety_result = generator.generate(config, skip_safety_check=False)

        if safety_result.ok:
            out_path.write_text(code, encoding="utf-8")
            console.print(f"[green]✓[/] {model}: {out_path}")
        else:
            console.print(f"[red]✗[/] {model}: safety validation failed")
            console.print(f"  {safety_result.summary()}")

    console.print(f"\n[cyan]Output directory:[/] {out_dir}")
    console.print("[yellow]★ Tier 3 — a human must review before running.[/]")


# ===========================================================================
# P2 · P4 · P5 · P6 commands — wired from maglab/commands/
# ===========================================================================

p2_analysis.register(app)
p4_ralph.register(app)
p5_literature.register(app)
p6_authoring.register(app)
