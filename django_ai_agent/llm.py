"""
django_ai_agent/llm.py

LLM factory for django-langgraph-agent.

Builds a ChatOpenAI instance pointing at OpenRouter with an automatic
multi-model fallback chain and connection retry logic.

  Primary → model or DJANGO_AI_AGENT["DEFAULT_MODEL"]
  Fallback → DJANGO_AI_AGENT["FALLBACK_MODELS"] in order
"""

import logging

from openai import APIConnectionError, APIStatusError, NotFoundError, RateLimitError

from .conf import agent_settings

logger = logging.getLogger(__name__)


def build_llm(model: str | None = None, title: str | None = None, max_tokens: int | None = None):
    """
    Returns a ChatOpenAI LLM configured for OpenRouter with a fallback chain.

    Args:
        model:      Optional model string override (e.g. 'google/gemini-2.5-flash').
        title:      HTTP-Referer / X-Title header sent to OpenRouter.
                    Defaults to DJANGO_AI_AGENT["SITE_TITLE"].
        max_tokens: Max tokens for the response.
                    Defaults to DJANGO_AI_AGENT["MAX_TOKENS"].

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
            "Add it to DJANGO_AI_AGENT['OPENROUTER_API_KEY'] in your settings."
        )

    site_title = title or agent_settings.SITE_TITLE
    site_url = agent_settings.SITE_URL
    max_tok = max_tokens or agent_settings.MAX_TOKENS

    def _make(model_name: str) -> ChatOpenAI:
        return ChatOpenAI(
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=api_key,
            model_name=model_name,
            max_tokens=max_tok,
            max_retries=3,
            request_timeout=30.0,
            default_headers={
                "HTTP-Referer": site_url,
                "X-Title": site_title,
            },
        )

    primary_model = model or agent_settings.DEFAULT_MODEL
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
    Uses DJANGO_AI_AGENT["SUMMARIZER_MODEL"] (defaults to deepseek-chat).
    """
    from langchain_openai import ChatOpenAI

    api_key = agent_settings.OPENROUTER_API_KEY
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    return ChatOpenAI(
        openai_api_base="https://openrouter.ai/api/v1",
        openai_api_key=api_key,
        model_name=agent_settings.SUMMARIZER_MODEL,
        max_tokens=300,
        max_retries=3,
        request_timeout=30.0,
        default_headers={
            "HTTP-Referer": agent_settings.SITE_URL,
            "X-Title": f"{agent_settings.SITE_TITLE} Summarizer",
        },
    )
