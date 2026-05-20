"""Provider profiles for MagLab LLM backends.

This module is the single place where MagLab maps user-facing provider names
to LiteLLM provider prefixes, API-key environment variables, default models,
stage routing, and provider-specific runtime instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from maglab.config import Config

PROMPT_DIR = Path(__file__).parent / "prompts" / "providers"


@dataclass(frozen=True)
class ProviderProfile:
    """Runtime configuration for one LLM provider."""

    key: str
    title: str
    litellm_provider: str
    model_prefix: str
    maglab_env_var: str
    litellm_env_var: str
    default_model: str
    routing: dict[str, str]
    prompt_file: str
    models: tuple[str, ...] = ()
    direct_env_vars: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def _routing(
    plan: str, build: str, summarize: str, vision_critic: str | None = None
) -> dict[str, str]:
    return {
        "plan": plan,
        "build": build,
        "summarize": summarize,
        "vision_critic": vision_critic or plan,
    }


API_PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "anthropic": ProviderProfile(
        key="anthropic",
        title="Anthropic Claude",
        litellm_provider="anthropic",
        model_prefix="anthropic/",
        maglab_env_var="MAGLAB_ANTHROPIC_API_KEY",
        litellm_env_var="ANTHROPIC_API_KEY",
        default_model="claude-opus-4-7",
        routing=_routing(
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ),
        prompt_file="claude.md",
        models=(
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-6",
            "claude-sonnet-4-5",
            "claude-opus-4-1-20250805",
        ),
        direct_env_vars=("ANTHROPIC_API_KEY",),
        aliases=("claude",),
        notes=(
            "Uses Claude-oriented long-context planning and explicit tool/provenance discipline.",
        ),
    ),
    "grok": ProviderProfile(
        key="grok",
        title="xAI Grok",
        litellm_provider="xai",
        model_prefix="xai/",
        maglab_env_var="MAGLAB_GROK_API_KEY",
        litellm_env_var="XAI_API_KEY",
        default_model="xai/grok-4.3",
        routing=_routing("xai/grok-4.3", "xai/grok-4.3", "xai/grok-4.3"),
        prompt_file="grok.md",
        models=(
            "xai/grok-4.3",
            "xai/grok-4.3-latest",
            "xai/grok-latest",
            "xai/grok-4.20",
        ),
        direct_env_vars=("XAI_API_KEY", "GROK_API_KEY"),
        aliases=("xai",),
        notes=("Uses xAI's OpenAI-compatible endpoint through LiteLLM.",),
    ),
    "deepseek": ProviderProfile(
        key="deepseek",
        title="DeepSeek",
        litellm_provider="deepseek",
        model_prefix="deepseek/",
        maglab_env_var="MAGLAB_DEEPSEEK_API_KEY",
        litellm_env_var="DEEPSEEK_API_KEY",
        default_model="deepseek/deepseek-v4-pro",
        routing=_routing(
            "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-flash"
        ),
        prompt_file="deepseek.md",
        models=(
            "deepseek/deepseek-v4-pro",
            "deepseek/deepseek-v4-flash",
            "deepseek/deepseek-reasoner",
            "deepseek/deepseek-chat",
        ),
        direct_env_vars=("DEEPSEEK_API_KEY",),
        notes=(
            "V4-Pro is preferred for planning; V4-Flash is preferred for tool iteration and summaries.",
            "deepseek-chat and deepseek-reasoner remain accepted compatibility aliases until their announced deprecation.",
        ),
    ),
    "qwen": ProviderProfile(
        key="qwen",
        title="Alibaba Qwen",
        litellm_provider="dashscope",
        model_prefix="dashscope/",
        maglab_env_var="MAGLAB_QWEN_API_KEY",
        litellm_env_var="DASHSCOPE_API_KEY",
        default_model="dashscope/qwen3.6-plus",
        routing=_routing(
            "dashscope/qwen3.6-max-preview",
            "dashscope/qwen3.6-plus",
            "dashscope/qwen3.6-flash",
        ),
        prompt_file="qwen.md",
        models=(
            "dashscope/qwen3.6-plus",
            "dashscope/qwen3.6-max-preview",
            "dashscope/qwen3.6-flash",
            "dashscope/qwen3.6-plus-2026-04-02",
            "dashscope/qwen3.6-flash-2026-04-16",
            "dashscope/qwen3.6-35b-a3b",
            "dashscope/qwen3.6-27b",
            "dashscope/qwen3.5-plus",
            "dashscope/qwen3.5-plus-2026-04-20",
            "dashscope/qwen3.5-flash",
            "dashscope/qwen3.5-flash-2026-02-23",
            "dashscope/qwen3-max",
            "dashscope/qwen3-max-2026-01-23",
            "dashscope/qwen3-coder-plus",
            "dashscope/qwen3-coder-flash",
        ),
        direct_env_vars=("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
        aliases=("dashscope", "alibaba"),
        notes=("Uses DashScope OpenAI-compatible mode through LiteLLM.",),
    ),
    "kimi": ProviderProfile(
        key="kimi",
        title="Moonshot Kimi",
        litellm_provider="moonshot",
        model_prefix="moonshot/",
        maglab_env_var="MAGLAB_KIMI_API_KEY",
        litellm_env_var="MOONSHOT_API_KEY",
        default_model="moonshot/kimi-k2.6",
        routing=_routing("moonshot/kimi-k2.6", "moonshot/kimi-k2.6", "moonshot/kimi-k2.5"),
        prompt_file="kimi.md",
        models=(
            "moonshot/kimi-k2.6",
            "moonshot/kimi-k2.5",
            "moonshot/kimi-k2-thinking",
            "moonshot/kimi-k2-thinking-turbo",
            "moonshot/kimi-k2-turbo-preview",
            "moonshot/kimi-k2-0905-preview",
            "moonshot/moonshot-v1-8k",
            "moonshot/moonshot-v1-32k",
            "moonshot/moonshot-v1-128k",
            "moonshot/moonshot-v1-8k-vision-preview",
            "moonshot/moonshot-v1-32k-vision-preview",
            "moonshot/moonshot-v1-128k-vision-preview",
        ),
        direct_env_vars=("MOONSHOT_API_KEY", "KIMI_API_KEY"),
        aliases=("moonshot",),
        notes=(
            "Uses Moonshot/Kimi; keeps prompts compact unless a long-context Kimi model is selected.",
        ),
    ),
    "gemini": ProviderProfile(
        key="gemini",
        title="Google Gemini",
        litellm_provider="gemini",
        model_prefix="gemini/",
        maglab_env_var="MAGLAB_GEMINI_API_KEY",
        litellm_env_var="GEMINI_API_KEY",
        default_model="gemini/gemini-3.1-pro-preview",
        routing=_routing(
            "gemini/gemini-3.1-pro-preview",
            "gemini/gemini-3.5-flash",
            "gemini/gemini-3.1-flash-lite",
        ),
        prompt_file="gemini.md",
        models=(
            "gemini/gemini-3.1-pro-preview",
            "gemini/gemini-3.1-pro-preview-customtools",
            "gemini/gemini-3.5-flash",
            "gemini/gemini-3-flash-preview",
            "gemini/gemini-3.1-flash-lite",
            "gemini/gemini-2.5-pro",
            "gemini/gemini-2.5-flash",
            "gemini/gemini-2.5-flash-lite",
            "gemini/gemini-2.5-flash-preview-09-2025",
            "gemini/gemini-2.5-flash-lite-preview-09-2025",
        ),
        direct_env_vars=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        aliases=("google",),
        notes=(
            "Uses Gemini through LiteLLM; old provider name 'google' is accepted as an alias.",
            "Gemini 3 Pro Preview is intentionally omitted because Google shut it down on 2026-03-09.",
        ),
    ),
    "openai": ProviderProfile(
        key="openai",
        title="OpenAI",
        litellm_provider="openai",
        model_prefix="",
        maglab_env_var="MAGLAB_OPENAI_API_KEY",
        litellm_env_var="OPENAI_API_KEY",
        default_model="gpt-5.5",
        routing=_routing("gpt-5.5", "gpt-5.4", "gpt-5.4-mini"),
        prompt_file="openai.md",
        models=(
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-5.2",
            "gpt-5.3-codex",
            "gpt-5-mini",
            "gpt-4.1",
        ),
        direct_env_vars=("OPENAI_API_KEY",),
        aliases=(),
        notes=("Uses OpenAI chat models directly through LiteLLM.",),
    ),
    "openai-compatible": ProviderProfile(
        key="openai-compatible",
        title="OpenAI-compatible endpoint",
        litellm_provider="openai",
        model_prefix="",
        maglab_env_var="MAGLAB_OPENAI_COMPATIBLE_API_KEY",
        litellm_env_var="OPENAI_API_KEY",
        default_model="gpt-5.4-mini",
        routing=_routing("gpt-5.5", "gpt-5.4", "gpt-5.4-mini"),
        prompt_file="openai.md",
        models=(
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "local-model",
            "llama3.1",
            "qwen3.5-coder",
            "deepseek-v4-flash",
        ),
        direct_env_vars=("OPENAI_COMPATIBLE_API_KEY",),
        aliases=("compatible", "openai_like", "openai-like"),
        notes=("Requires backend.api.base_url or --base-url for the target endpoint.",),
    ),
}


DELEGATED_PROMPT_FILES: dict[str, str] = {
    "codex": "codex.md",
    "claude": "claude.md",
    "gemini": "gemini.md",
}


LOCAL_PROMPT_FILE = "ollama.md"


DELEGATED_MODEL_CHOICES: dict[str, tuple[str, ...]] = {
    "codex": (
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex",
        "gpt-5.2",
        "gpt-5-mini",
    ),
    "claude": ("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"),
    "gemini": (
        "gemini-3.1-pro-preview",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ),
}


_ALIASES: dict[str, str] = {
    alias: key
    for key, profile in API_PROVIDER_PROFILES.items()
    for alias in (profile.key, *profile.aliases)
}


def normalize_provider(provider: str) -> str:
    """Return the canonical MagLab provider key."""
    key = provider.strip().lower().replace("_", "-")
    return _ALIASES.get(key, key)


def get_provider_profile(provider: str) -> ProviderProfile:
    """Return a provider profile, accepting aliases."""
    key = normalize_provider(provider)
    try:
        return API_PROVIDER_PROFILES[key]
    except KeyError as exc:
        valid = ", ".join(api_provider_keys())
        raise ValueError(
            f"Unknown LLM provider {provider!r}. Supported providers: {valid}"
        ) from exc


def api_provider_keys() -> list[str]:
    """Return canonical direct-API provider keys shown in CLI help."""
    return [
        "anthropic",
        "grok",
        "deepseek",
        "qwen",
        "kimi",
        "gemini",
        "openai",
        "openai-compatible",
    ]


def api_provider_choices() -> str:
    """Return a compact provider list for terminal help."""
    return "·".join(api_provider_keys())


def model_choices(provider: str) -> tuple[str, ...]:
    """Return curated model choices for terminal dropdowns and completion menus."""
    profile = get_provider_profile(provider)
    if profile.models:
        return profile.models
    return (profile.default_model,)


def delegated_model_choices(tool: str) -> tuple[str, ...]:
    """Return curated model choices for delegated CLI backends."""
    return DELEGATED_MODEL_CHOICES.get(tool.strip().lower(), ())


def build_litellm_model(provider: str, model: str | None = None) -> str:
    """Return the LiteLLM model string for a MagLab provider/model pair."""
    profile = get_provider_profile(provider)
    resolved = (model or profile.default_model).strip()
    if profile.model_prefix and not resolved.startswith(profile.model_prefix):
        return profile.model_prefix + resolved
    return resolved


def is_model_compatible(provider: str, model: str | None) -> bool:
    """Heuristic guard to avoid routing a Claude model into a non-Claude backend."""
    if model is None:
        return True
    value = model.strip()
    if not value:
        return True
    profile = get_provider_profile(provider)
    if profile.key == "openai-compatible":
        return True
    if profile.model_prefix:
        if value.startswith(profile.model_prefix):
            return True
        # Allow unprefixed provider-native model names because CLI users often
        # pass vendor docs names rather than LiteLLM-prefixed names.
        if profile.key == "anthropic" and value.startswith("claude-"):
            return True
        if profile.key == "grok" and value.startswith("grok-"):
            return True
        if profile.key == "deepseek" and value.startswith("deepseek-"):
            return True
        if profile.key == "qwen" and value.startswith("qwen"):
            return True
        if profile.key == "kimi" and value.startswith("kimi-"):
            return True
        return profile.key == "gemini" and value.startswith("gemini-")
    # OpenAI models should not be overwritten by another provider's route.
    blocked_prefixes = (
        "claude-",
        "gemini-",
        "grok-",
        "deepseek-",
        "qwen-",
        "kimi-",
        "xai/",
        "deepseek/",
        "dashscope/",
        "moonshot/",
    )
    return not value.startswith(blocked_prefixes)


def provider_prompt_for_file(prompt_file: str) -> str:
    """Load a provider prompt file from the package."""
    path = PROMPT_DIR / prompt_file
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def prompt_for_config(config: Config) -> str:
    """Return runtime-specific system prompt guidance for the configured backend."""
    mode = config.backend.mode
    if mode == "api":
        profile = get_provider_profile(config.backend.api.provider)
        text = provider_prompt_for_file(profile.prompt_file)
        return f"Runtime provider: {profile.title} API ({profile.key}).\n\n{text}".strip()
    if mode == "delegated_cli":
        tool = config.backend.delegated_cli.tool.strip().lower()
        text = provider_prompt_for_file(DELEGATED_PROMPT_FILES.get(tool, "openai.md"))
        return f"Runtime provider: delegated {tool} CLI.\n\n{text}".strip()
    if mode == "local":
        text = provider_prompt_for_file(LOCAL_PROMPT_FILE)
        return f"Runtime provider: local Ollama ({config.backend.local.model}).\n\n{text}".strip()
    return ""
