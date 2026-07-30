"""
django_ai_agent/models.py

Django models for django-langgraph-agent.

AgentConfig   — DB-backed agent definition, manageable from Django Admin.
ChatThread    — Optional: persists conversation threads per user/agent.
ChatMessage   — Optional: persists individual messages (AI + user).
"""

from django.conf import settings
from django.db import models


class AgentConfig(models.Model):
    """
    A database-backed AI agent configuration.

    Developers define agents in the Django Admin without touching code.
    Tools are referenced by name (strings) and resolved via the tool registry
    at runtime.
    """

    name = models.SlugField(
        max_length=100,
        unique=True,
        help_text=(
            "Unique slug for this agent (e.g. 'support', 'admin-bot'). "
            "Used in API URLs: POST /agent/chat/?agent=support"
        ),
    )
    display_name = models.CharField(
        max_length=200,
        help_text="Human-readable name shown in the admin.",
    )
    system_prompt = models.TextField(
        help_text=(
            "The agent's personality and instructions. "
            "Supports {user_id}, {date}, {summary} placeholders — see docs."
        ),
    )
    model_name = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "OpenRouter model ID to use (e.g. 'google/gemini-2.5-flash'). "
            "Leave blank to use DJANGO_AI_AGENT['DEFAULT_MODEL']."
        ),
    )
    max_tokens = models.IntegerField(
        null=True,
        blank=True,
        help_text="Max response tokens. Leave blank to use DJANGO_AI_AGENT['MAX_TOKENS'].",
    )
    summary_threshold = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "Number of messages before conversation is summarized. "
            "Leave blank to use DJANGO_AI_AGENT['SUMMARY_THRESHOLD']."
        ),
    )
    allowed_models = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Whitelisted Django models allowed for this agent (e.g. ["store.Product", "store.Order"]). '
            'Leave empty to inherit all models configured in settings.py.'
        ),
    )
    blocked_fields = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Field names or substrings blocked for this agent (e.g. ["password", "is_superuser"]). '
            'Leave empty to inherit global default blocked fields.'
        ),
    )
    extra_tools = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Names of ADDITIONAL registered tools to add on top of the built-in ORM tools. '
            'Built-in tools (get_model_schema, query_records, aggregate_model_records, add_record, update_record) '
            'are always included automatically. '
            'Add custom tools here: e.g. ["send_email", "send_push_notification"]. '
            'Each name must be registered with @register_tool in your code.'
        ),
    )
    extra_approval_tools = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Extra tool names (beyond add_record and update_record) that require '
            'explicit user approval before execution. '
            'e.g. ["send_email", "send_push_notification"]'
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive agents reject API requests with 404.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Agent Configuration"
        verbose_name_plural = "Agent Configurations"
        ordering = ["name"]

    def __str__(self):
        status = "✅" if self.is_active else "❌"
        return f"{status} {self.display_name} [{self.name}]"

    def get_all_tools(self) -> list:
        from .tools.django_orm import (
            get_model_schema,
            query_records,
            aggregate_model_records,
            add_record,
            update_record,
        )
        from .registry import get_tool

        builtin = [get_model_schema, query_records, aggregate_model_records, add_record, update_record]
        extra = []
        for name in (self.extra_tools or []):
            try:
                extra.append(get_tool(name))
            except KeyError as exc:
                import logging
                logging.getLogger(__name__).warning(str(exc))

        return builtin + extra

    def get_all_approval_tools(self) -> set:
        defaults = {"add_record", "update_record"}
        return defaults | set(self.extra_approval_tools or [])

    def to_django_agent(self):
        """Instantiates and returns a DjangoAgent from this DB configuration."""
        from .agent import DjangoAgent
        return DjangoAgent(
            name=self.name,
            system_prompt=self.system_prompt,
            tools=self.get_all_tools(),
            model_name=self.model_name or None,
            max_tokens=self.max_tokens,
            summary_threshold=self.summary_threshold,
            approval_tools=self.get_all_approval_tools(),
            allowed_models=self.allowed_models or [],
            blocked_fields=self.blocked_fields or [],
        )


class ChatThread(models.Model):
    thread_id = models.CharField(
        max_length=200,
        primary_key=True,
        help_text="Unique thread identifier string.",
    )
    agent = models.ForeignKey(
        AgentConfig,
        on_delete=models.CASCADE,
        related_name="threads",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_threads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Chat Thread"
        verbose_name_plural = "Chat Threads"
        ordering = ["-updated_at"]

    def __str__(self):
        user_str = f" user={self.user}" if self.user else ""
        return f"Thread[{self.thread_id[:16]}…]{user_str} ({self.agent.name})"


class ChatMessage(models.Model):
    thread = models.ForeignKey(
        ChatThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    text = models.TextField()
    is_user = models.BooleanField(
        help_text="True if sent by human user, False if generated by AI.",
    )
    model_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="OpenRouter model name used for generation (if AI message).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"
        ordering = ["created_at"]

    def __str__(self):
        sender = "👤 User" if self.is_user else "🤖 AI"
        return f"[{sender}] {self.text[:40]}…"
