"""
django_langgraph_agent/conf.py

Settings reader for django-langgraph-agent.
"""

from django.conf import settings as django_settings

DEFAULTS = {
    "OPENROUTER_API_KEY": None,
    "DEFAULT_MODEL": "google/gemini-3.5-flash-lite",
    "FALLBACK_MODELS": ["google/gemini-2.0-flash-001", "openai/gpt-4o-mini"],
    "SUMMARIZER_MODEL": "google/gemini-3.5-flash-lite",
    "MAX_TOKENS": 800,
    "SUMMARY_THRESHOLD": 4,
    "SITE_URL": "https://example.com",
    "SITE_TITLE": "Django LangGraph Agent",
    "APPROVAL_REQUIRED_TOOLS": [],
    "MODEL_WHITELIST": {},
    "BLOCKED_FIELD_SUBSTRINGS": ["password", "token", "secret", "is_superuser", "is_staff"],
    "PERSIST_MESSAGES": False,
}


class _AgentSettings:
    """
    Lazy proxy that reads DJANGO_LANGGRAPH_AGENT (or DJANGO_AI_AGENT) from Django settings,
    merging with DEFAULTS. Attribute access is cached after first read.
    """

    def __init__(self):
        self._cache = {}

    def _load(self):
        user_conf = getattr(django_settings, "DJANGO_LANGGRAPH_AGENT", None)
        if user_conf is None:
            user_conf = getattr(django_settings, "DJANGO_AI_AGENT", {})
        merged = {**DEFAULTS, **user_conf}
        self._cache = merged

    def __getattr__(self, name):
        if not self._cache:
            self._load()
        if name in self._cache:
            return self._cache[name]
        raise AttributeError(f"django-langgraph-agent has no setting '{name}'")

    def reload(self):
        """Force re-read from Django settings (useful in tests)."""
        self._cache = {}
        self._load()


agent_settings = _AgentSettings()

