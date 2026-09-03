"""
django_langgraph_agent/conf.py

Settings reader for django-langgraph-agent.
"""

from django.core.signals import setting_changed
from django.conf import settings as django_settings
from django.dispatch import receiver

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

    # ── Upstream LLM endpoint ────────────────────────────────────────────────
    # OpenAI-compatible base URL every ChatOpenAI instance is pointed at.
    # Override to leave OpenRouter entirely (e.g. Google AI Studio's own
    # OpenAI-compatible endpoint, a local vLLM, or an internal gateway).
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    # OpenRouter upstream-provider routing, sent as extra_body["provider"].
    # Accepts OpenRouter's provider object, e.g.
    #   {"order": ["google-ai-studio"], "allow_fallbacks": False}
    # A bare string or list is expanded to {"order": [...]}. Without this,
    # OpenRouter picks the route itself — for Gemini that is the pricier
    # Vertex-billed one.
    "OPENROUTER_PROVIDER": None,
    # Arbitrary extra JSON merged into every request body (OpenRouter's
    # "transforms", "route", "reasoning", …). OPENROUTER_PROVIDER wins over a
    # "provider" key set here.
    "EXTRA_BODY": {},
    # Passed straight through to ChatOpenAI(**MODEL_KWARGS) — an escape hatch
    # for constructor arguments this package does not model.
    "MODEL_KWARGS": {},

    # ── Built-in API endpoint security ───────────────────────────────────────
    # Who may call the SSE endpoints exposed by include("django_langgraph_agent.urls").
    #   "staff"          → request.user.is_staff (default — matches the chat UI)
    #   "authenticated"  → any logged-in user
    #   "public"         → no check (opt-in; these endpoints drive the ORM tools)
    #   "app.module.fn"  → dotted path to callable(request) -> bool
    "API_PERMISSION": "staff",
    # CSRF stays on by default; the bundled chat template already sends X-CSRFToken.
    "API_CSRF_EXEMPT": False,
    # Trust a client-supplied "user_id" in the request body when the caller is
    # not authenticated. Off by default — it lets a caller impersonate any user.
    "TRUST_BODY_USER_ID": False,

    # ── Row-level scoping for the built-in ORM tools ─────────────────────────
    # callable(model, config) -> QuerySet | dict of filter kwargs | None
    #   Returns the base queryset every read/update is restricted to.
    #   Return None to leave that model unscoped; return model.objects.none()
    #   to deny access outright.
    "QUERYSET_SCOPE": None,
    # callable(model, config) -> dict of field values force-applied to every
    # add_record / update_record write (e.g. {"organization_id": 7}). Applied
    # after field validation, so concrete "<fk>_id" keys are allowed here.
    "WRITE_DEFAULTS": None,
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


@receiver(setting_changed)
def _reset_on_setting_changed(sender, setting, **kwargs):
    """Drops the cache when DJANGO_LANGGRAPH_AGENT changes (override_settings)."""
    if setting in ("DJANGO_LANGGRAPH_AGENT", "DJANGO_AI_AGENT"):
        agent_settings._cache = {}

