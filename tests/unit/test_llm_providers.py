"""Provider profile tests for MagLab LLM backends."""

from __future__ import annotations

from maglab.config import Config
from maglab.llm.providers import (
    build_litellm_model,
    delegated_model_choices,
    get_provider_profile,
    is_model_compatible,
    model_choices,
    normalize_provider,
    prompt_for_config,
)


def test_provider_aliases_normalize_to_canonical_keys() -> None:
    assert normalize_provider("claude") == "anthropic"
    assert normalize_provider("xai") == "grok"
    assert normalize_provider("google") == "gemini"
    assert normalize_provider("dashscope") == "qwen"
    assert normalize_provider("moonshot") == "kimi"


def test_litellm_model_prefixes_are_provider_specific() -> None:
    assert build_litellm_model("grok", "grok-4.20") == "xai/grok-4.20"
    assert build_litellm_model("deepseek", "deepseek-v4-pro") == "deepseek/deepseek-v4-pro"
    assert build_litellm_model("deepseek", "deepseek-chat") == "deepseek/deepseek-chat"
    assert build_litellm_model("qwen", "qwen3.6-plus") == "dashscope/qwen3.6-plus"
    assert build_litellm_model("kimi", "kimi-k2.6") == "moonshot/kimi-k2.6"
    assert (
        build_litellm_model("gemini", "gemini-3.1-pro-preview") == "gemini/gemini-3.1-pro-preview"
    )
    assert build_litellm_model("openai", "gpt-5.5") == "gpt-5.5"


def test_model_compatibility_blocks_cross_provider_route_leaks() -> None:
    assert is_model_compatible("openai", "claude-opus-4-7") is False
    assert is_model_compatible("openai", "gemini-2.5-pro") is False
    assert is_model_compatible("grok", "claude-opus-4-7") is False
    assert is_model_compatible("anthropic", "claude-opus-4-7") is True
    assert is_model_compatible("qwen", "qwen3.6-plus") is True
    assert is_model_compatible("qwen", "dashscope/qwen3.6-plus") is True


def test_provider_profile_contains_maglab_secret_envs() -> None:
    assert get_provider_profile("grok").maglab_env_var == "MAGLAB_GROK_API_KEY"
    assert get_provider_profile("qwen").litellm_env_var == "DASHSCOPE_API_KEY"
    assert get_provider_profile("kimi").litellm_env_var == "MOONSHOT_API_KEY"


def test_model_choices_include_current_provider_defaults() -> None:
    assert model_choices("anthropic")[0] == "claude-opus-4-7"
    assert model_choices("grok")[0] == "xai/grok-4.3"
    assert "xai/grok-4.3" in model_choices("grok")
    assert "deepseek/deepseek-v4-pro" in model_choices("deepseek")
    assert "deepseek/deepseek-chat" in model_choices("deepseek")
    assert model_choices("qwen")[0] == "dashscope/qwen3.6-plus"
    assert "dashscope/qwen3.6-max-preview" in model_choices("qwen")
    assert "dashscope/qwen3.6-35b-a3b" in model_choices("qwen")
    assert "moonshot/kimi-k2.6" in model_choices("kimi")
    assert "moonshot/kimi-k2-thinking" in model_choices("kimi")
    assert "moonshot/moonshot-v1-128k-vision-preview" in model_choices("kimi")
    assert model_choices("gemini")[0] == "gemini/gemini-3.1-pro-preview"
    assert "gemini/gemini-3.5-flash" in model_choices("gemini")
    assert "gemini/gemini-3.1-flash-lite" in model_choices("gemini")
    assert "gemini/gemini-3-pro-preview" not in model_choices("gemini")
    assert "gemini/gemini-2.5-flash-lite-preview-09-2025" in model_choices("gemini")
    assert model_choices("openai")[0] == "gpt-5.5"
    assert "gpt-5.4-nano" in model_choices("openai")
    assert "gpt-5.5" in model_choices("openai")
    assert "gpt-5.5" in delegated_model_choices("codex")
    assert "gpt-5.4-mini" in delegated_model_choices("codex")
    assert "gemini-3.1-pro-preview" in delegated_model_choices("gemini")


def test_prompt_for_delegated_codex_identifies_maglab_agent() -> None:
    cfg = Config.model_validate(
        {
            "backend": {
                "mode": "delegated_cli",
                "delegated_cli": {"tool": "codex", "model": None},
            }
        }
    )

    prompt = prompt_for_config(cfg)

    assert "MagLab research orchestration agent" in prompt
    assert "delegated codex CLI" in prompt
