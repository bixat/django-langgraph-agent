"""
django_ai_agent/apps.py

Django AppConfig for django-langgraph-agent.

Handles startup:
  - Validates required settings
  - Auto-registers built-in ORM tools into the tool registry
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class DjangoAIAgentConfig(AppConfig):
    name = "django_ai_agent"
    verbose_name = "Django AI Agent"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        """Called once when Django starts."""
        self._validate_settings()
        self._register_builtin_tools()

    def _validate_settings(self):
        from .conf import agent_settings
        if not agent_settings.OPENROUTER_API_KEY:
            logger.warning(
                "django-langgraph-agent: OPENROUTER_API_KEY is not set in "
                "DJANGO_AI_AGENT settings. Agents will fail at runtime."
            )

    def _register_builtin_tools(self):
        """Auto-register the 4 built-in ORM tools so they appear in admin."""
        from .registry import _register_builtin_tools
        _register_builtin_tools()
