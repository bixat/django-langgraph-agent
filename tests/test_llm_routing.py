"""
tests/test_llm_routing.py

Covers issue #9: OpenRouter upstream-provider routing, base URL and extra
ChatOpenAI kwargs must all be reachable from settings, including on the
DB-backed path where AgentConfig.to_django_agent() never passes an `llm`.
"""

import pytest
from django.test import override_settings

from django_langgraph_agent import llm as llm_module


BASE = {
    "OPENROUTER_API_KEY": "test-key",
    "DEFAULT_MODEL": "google/gemini-3-flash-preview",
    "FALLBACK_MODELS": [],
}


def _settings(**extra):
    return {**BASE, **extra}


# ──────────────────────────────────────────────────────────────────────────────
# Provider normalisation
# ──────────────────────────────────────────────────────────────────────────────

def test_no_provider_configured_sends_no_extra_body():
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings()):
        assert llm_module._provider_routing() is None
        assert llm_module._extra_body() == {}


def test_provider_string_is_shorthand_for_order():
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(OPENROUTER_PROVIDER="google-ai-studio")):
        assert llm_module._provider_routing() == {"order": ["google-ai-studio"]}


def test_provider_list_is_shorthand_for_order():
    with override_settings(
        DJANGO_LANGGRAPH_AGENT=_settings(OPENROUTER_PROVIDER=["google-ai-studio", "google-vertex"])
    ):
        assert llm_module._provider_routing() == {
            "order": ["google-ai-studio", "google-vertex"]
        }


def test_provider_dict_passes_through_untouched():
    provider = {"order": ["google-ai-studio"], "allow_fallbacks": False}
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(OPENROUTER_PROVIDER=provider)):
        assert llm_module._provider_routing() == provider


def test_provider_of_wrong_type_is_rejected():
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(OPENROUTER_PROVIDER=7)):
        with pytest.raises(ValueError, match="OPENROUTER_PROVIDER"):
            llm_module._provider_routing()


# ──────────────────────────────────────────────────────────────────────────────
# extra_body assembly
# ──────────────────────────────────────────────────────────────────────────────

def test_extra_body_merges_with_provider():
    with override_settings(
        DJANGO_LANGGRAPH_AGENT=_settings(
            EXTRA_BODY={"transforms": ["middle-out"]},
            OPENROUTER_PROVIDER="google-ai-studio",
        )
    ):
        assert llm_module._extra_body() == {
            "transforms": ["middle-out"],
            "provider": {"order": ["google-ai-studio"]},
        }


def test_provider_setting_wins_over_provider_key_in_extra_body():
    with override_settings(
        DJANGO_LANGGRAPH_AGENT=_settings(
            EXTRA_BODY={"provider": {"order": ["google-vertex"]}},
            OPENROUTER_PROVIDER="google-ai-studio",
        )
    ):
        assert llm_module._extra_body()["provider"] == {"order": ["google-ai-studio"]}


def test_extra_body_is_not_mutated_across_calls():
    body = {"transforms": ["middle-out"]}
    with override_settings(
        DJANGO_LANGGRAPH_AGENT=_settings(EXTRA_BODY=body, OPENROUTER_PROVIDER="google-ai-studio")
    ):
        llm_module._extra_body()
        llm_module._extra_body()
    assert body == {"transforms": ["middle-out"]}, "EXTRA_BODY setting was mutated in place"


# ──────────────────────────────────────────────────────────────────────────────
# ChatOpenAI kwargs
# ──────────────────────────────────────────────────────────────────────────────

def test_base_url_defaults_to_openrouter():
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings()):
        kwargs = llm_module._chat_openai_kwargs("m", 100, "t", "u")
    assert kwargs["openai_api_base"] == "https://openrouter.ai/api/v1"
    assert "extra_body" not in kwargs, "no extra_body should be sent when nothing is configured"


def test_base_url_is_overridable():
    with override_settings(
        DJANGO_LANGGRAPH_AGENT=_settings(
            OPENROUTER_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
        )
    ):
        kwargs = llm_module._chat_openai_kwargs("m", 100, "t", "u")
    assert kwargs["openai_api_base"] == "https://generativelanguage.googleapis.com/v1beta/openai"


def test_model_kwargs_are_forwarded():
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(MODEL_KWARGS={"temperature": 0.2})):
        kwargs = llm_module._chat_openai_kwargs("m", 100, "t", "u")
    assert kwargs["temperature"] == 0.2


# ──────────────────────────────────────────────────────────────────────────────
# End to end: the built LLM actually carries the routing
# ──────────────────────────────────────────────────────────────────────────────

def test_build_llm_applies_provider_to_primary_and_every_fallback():
    provider = {"order": ["google-ai-studio"], "allow_fallbacks": False}
    with override_settings(
        DJANGO_LANGGRAPH_AGENT={
            **BASE,
            "FALLBACK_MODELS": ["deepseek/deepseek-chat", "openai/gpt-4o-mini"],
            "OPENROUTER_PROVIDER": provider,
        }
    ):
        chain = llm_module.build_llm()

    # with_fallbacks() wraps the primary in a RunnableWithFallbacks.
    runnables = [chain.runnable] + list(chain.fallbacks)
    assert len(runnables) == 3
    for runnable in runnables:
        assert runnable.extra_body == {"provider": provider}


def test_build_summarizer_llm_applies_provider():
    with override_settings(
        DJANGO_LANGGRAPH_AGENT=_settings(
            SUMMARIZER_MODEL="google/gemini-3-flash-preview",
            OPENROUTER_PROVIDER="google-ai-studio",
        )
    ):
        summarizer = llm_module.build_summarizer_llm()

    assert summarizer.extra_body == {"provider": {"order": ["google-ai-studio"]}}
    assert summarizer.max_tokens == 300
