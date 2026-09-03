"""
django_langgraph_agent/llm.py

LLM factory for django-langgraph-agent.

Builds a ChatOpenAI instance pointing at OpenRouter with an automatic
multi-model fallback chain and connection retry logic.

  Primary → model or DJANGO_LANGGRAPH_AGENT["DEFAULT_MODEL"]
  Fallback → DJANGO_LANGGRAPH_AGENT["FALLBACK_MODELS"] in order
"""

import logging

from openai import APIConnectionError, APIStatusError, NotFoundError, RateLimitError

from .conf import agent_settings

logger = logging.getLogger(__name__)


def _provider_routing() -> dict | None:
    """
    Normalises DJANGO_LANGGRAPH_AGENT["OPENROUTER_PROVIDER"] into OpenRouter's
    provider object.

    A bare string ("google-ai-studio") or a list of them is shorthand for
    {"order": [...]} — the common case, pinning the upstream route.
    """
    provider = getattr(agent_settings, "OPENROUTER_PROVIDER", None)
    if not provider:
        return None
    if isinstance(provider, str):
        return {"order": [provider]}
    if isinstance(provider, (list, tuple)):
        return {"order": list(provider)}
    if isinstance(provider, dict):
        return provider
    raise ValueError(
        "DJANGO_LANGGRAPH_AGENT['OPENROUTER_PROVIDER'] must be a str, list or dict, "
        f"got {type(provider).__name__}."
    )


def _extra_body() -> dict:
    """Merges EXTRA_BODY with the normalised provider routing."""
    body = dict(getattr(agent_settings, "EXTRA_BODY", None) or {})
    provider = _provider_routing()
    if provider is not None:
        body["provider"] = provider
    return body


def _chat_openai_kwargs(model_name: str, max_tok: int, title: str, site_url: str) -> dict:
    """Builds the full ChatOpenAI(**kwargs) for one model."""
    kwargs = {
        "openai_api_base": getattr(
            agent_settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ),
        "openai_api_key": agent_settings.OPENROUTER_API_KEY,
        "model_name": model_name,
        "max_tokens": max_tok,
        "max_retries": 3,
        "request_timeout": 30.0,
        "default_headers": {
            "HTTP-Referer": site_url,
            "X-Title": title,
        },
    }
    extra_body = _extra_body()
    if extra_body:
        kwargs["extra_body"] = extra_body
    kwargs.update(getattr(agent_settings, "MODEL_KWARGS", None) or {})
    return kwargs


def build_llm(model: str | None = None, title: str | None = None, max_tokens: int | None = None):
    """
    Returns a ChatOpenAI LLM configured for OpenRouter with a fallback chain.

    Args:
        model:      Optional model string override (e.g. 'google/gemini-2.5-flash').
        title:      HTTP-Referer / X-Title header sent to OpenRouter.
                    Defaults to DJANGO_LANGGRAPH_AGENT["SITE_TITLE"].
        max_tokens: Max tokens for the response.
                    Defaults to DJANGO_LANGGRAPH_AGENT["MAX_TOKENS"].

    Returns:
        A ChatOpenAI instance (or a chained fallback wrapper).

    Raises:
        ValueError: If OPENROUTER_API_KEY is not set in settings.
    """
    from langchain_openai import ChatOpenAI

    api_key = agent_settings.OPENROUTER_API_KEY
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is not configured. "
            "Add it to DJANGO_LANGGRAPH_AGENT['OPENROUTER_API_KEY'] in your settings."
        )

    site_title = title or agent_settings.SITE_TITLE
    site_url = agent_settings.SITE_URL
    max_tok = max_tokens or agent_settings.MAX_TOKENS

    def _make(model_name: str) -> ChatOpenAI:
        return ChatOpenAI(**_chat_openai_kwargs(model_name, max_tok, site_title, site_url))

    primary_model = model.strip() if (model and isinstance(model, str) and model.strip()) else agent_settings.DEFAULT_MODEL
    primary = _make(primary_model)
    fallbacks = [_make(m) for m in agent_settings.FALLBACK_MODELS if m != primary_model]

    if fallbacks:
        return primary.with_fallbacks(
            fallbacks,
            exceptions_to_handle=(APIConnectionError, RateLimitError, APIStatusError, NotFoundError),
        )
    return primary


def build_summarizer_llm():
    """
    Builds a lightweight LLM used only for conversation summarization.
    Uses DJANGO_LANGGRAPH_AGENT["SUMMARIZER_MODEL"].
    """
    from langchain_openai import ChatOpenAI

    api_key = agent_settings.OPENROUTER_API_KEY
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    return ChatOpenAI(
        **_chat_openai_kwargs(
            agent_settings.SUMMARIZER_MODEL,
            300,
            f"{agent_settings.SITE_TITLE} Summarizer",
            agent_settings.SITE_URL,
        )
    )
