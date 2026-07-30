"""
django_ai_agent/migrations/0001_initial.py
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.SlugField(help_text="Unique slug for this agent (e.g. 'support', 'admin-bot'). Used in API: POST /agent/chat/?agent=support", max_length=100, unique=True)),
                ("display_name", models.CharField(help_text="Human-readable name shown in the admin.", max_length=200)),
                ("system_prompt", models.TextField(help_text="The agent's instructions. Supports {user_id}, {date}, {summary} placeholders.")),
                ("model_name", models.CharField(blank=True, help_text="OpenRouter model ID override. Leave blank to use DEFAULT_MODEL.", max_length=200)),
                ("max_tokens", models.IntegerField(blank=True, help_text="Max response tokens override.", null=True)),
                ("summary_threshold", models.IntegerField(blank=True, help_text="Message count before summarization. Leave blank to use SUMMARY_THRESHOLD.", null=True)),
                ("allowed_models", models.JSONField(blank=True, default=list, help_text='Whitelisted Django models allowed for this agent.')),
                ("blocked_fields", models.JSONField(blank=True, default=list, help_text='Field names or substrings blocked for this agent.')),
                ("extra_tools", models.JSONField(blank=True, default=list, help_text='Additional registered tool names beyond built-in ORM tools. e.g. ["send_email", "send_push_notification"]. Register with @register_tool first.')),
                ("extra_approval_tools", models.JSONField(blank=True, default=list, help_text='Extra tool names requiring user approval. add_record and update_record are always approval-gated by default.')),
                ("is_active", models.BooleanField(default=True, help_text="Inactive agents return 404.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Agent Configuration",
                "verbose_name_plural": "Agent Configurations",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ChatThread",
            fields=[
                ("thread_id", models.CharField(help_text="Unique thread identifier string.", max_length=200, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="threads", to="django_ai_agent.agentconfig")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_threads", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Chat Thread",
                "verbose_name_plural": "Chat Threads",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField()),
                ("is_user", models.BooleanField(help_text="True for user messages, False for AI responses.")),
                ("model_name", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="django_ai_agent.chatthread")),
            ],
            options={
                "verbose_name": "Chat Message",
                "verbose_name_plural": "Chat Messages",
                "ordering": ["created_at"],
            },
        ),
    ]
