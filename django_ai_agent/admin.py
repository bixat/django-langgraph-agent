"""
django_ai_agent/admin.py

Rich Django Admin for managing AI agents, threads, and messages (with Unfold support).
Features Autocomplete Multi-Select for Whitelisted Django Models and Blocked Fields.
"""

import json

from django import forms
from django.apps import apps
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

try:
    from unfold.admin import ModelAdmin, TabularInline
except ImportError:
    from django.contrib.admin import ModelAdmin, TabularInline

from .conf import agent_settings
from .models import AgentConfig, ChatMessage, ChatThread


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_all_django_models():
    """Returns a list of dict items for all installed Django models."""
    models_list = []
    for model_cls in apps.get_models():
        app_label = model_cls._meta.app_label
        if app_label in ("django_ai_agent", "admin", "sessions", "contenttypes"):
            continue
        label = f"{app_label}.{model_cls._meta.object_name}"
        display = f"{app_label} | {model_cls._meta.verbose_name.title()} ({model_cls._meta.object_name})"
        models_list.append({"value": label, "label": display})
    return sorted(models_list, key=lambda x: x["value"])


def _get_all_model_fields():
    """Returns a list of all unique field names across project models."""
    fields_set = set()
    for model_cls in apps.get_models():
        app_label = model_cls._meta.app_label
        if app_label in ("django_ai_agent", "admin", "sessions", "contenttypes"):
            continue
        for f in model_cls._meta.get_fields():
            if hasattr(f, "name"):
                fields_set.add(f.name)
    fields_set.update(["password", "token", "secret", "is_superuser", "is_staff", "ssn", "credit_card"])
    return sorted(fields_set)


def _available_tools_html():
    """Renders a collapsible list of registered tools for the admin help section."""
    try:
        from .registry import list_tools
        tools = list_tools()
        if not tools:
            return "<em>No custom tools registered yet.</em>"
        rows = "".join(
            f"<tr><td style='padding:4px 8px'><code>{name}</code></td><td style='padding:4px 8px'>{doc}</td></tr>"
            for name, doc in sorted(tools.items())
        )
        return mark_safe(
            "<details><summary><strong>📦 Registered tools available for extra_tools</strong></summary>"
            "<table style='margin-top:6px;border-collapse:collapse;width:100%'>"
            "<thead><tr><th style='text-align:left;padding:4px 8px'>Name</th>"
            "<th style='text-align:left;padding:4px 8px'>Description</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></details>"
        )
    except Exception:
        return ""


def _autocomplete_script_html():
    """
    Renders Autocomplete Multi-Select Tag controls for allowed_models and blocked_fields.
    Appended cleanly without creating fake empty fields or helper sections.
    """
    all_models = json.dumps(_get_all_django_models())
    all_fields = json.dumps(_get_all_model_fields())

    html = f"""
    <style>
        .auto-input-box {{
            background-color: #ffffff !important;
            color: #111827 !important;
            border-color: #d1d5db !important;
        }}

        .dark .auto-input-box {{
            background-color: #1f2937 !important;
            color: #ffffff !important;
            border-color: #374151 !important;
        }}

        .auto-tag {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-family: monospace;
            font-weight: 500;
            transition: all 0.15s ease;
        }}
        .auto-tag-model {{
            background-color: #ecfdf5 !important;
            color: #047857 !important;
            border: 1px solid #a7f3d0 !important;
        }}
        .dark .auto-tag-model {{
            background-color: #064e3b !important;
            color: #a7f3d0 !important;
            border-color: #047857 !important;
        }}
        .auto-tag-field {{
            background-color: #fef2f2 !important;
            color: #b91c1c !important;
            border: 1px solid #fecaca !important;
        }}
        .dark .auto-tag-field {{
            background-color: #7f1d1d !important;
            color: #fecaca !important;
            border-color: #991b1b !important;
        }}
        .auto-tag-remove {{
            cursor: pointer;
            font-weight: bold;
            font-size: 0.85rem;
            line-height: 1;
            opacity: 0.7;
        }}
        .auto-tag-remove:hover {{
            opacity: 1;
        }}
        .autocomplete-dropdown-fixed {{
            position: fixed !important;
            max-height: 220px;
            overflow-y: auto;
            background-color: #ffffff !important;
            color: #111827 !important;
            border: 1px solid #d1d5db !important;
            border-radius: 0.5rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3) !important;
            z-index: 999999 !important;
            display: none;
        }}
        .dark .autocomplete-dropdown-fixed {{
            background-color: #1f2937 !important;
            color: #f3f4f6 !important;
            border-color: #374151 !important;
        }}
        .autocomplete-item {{
            padding: 8px 12px;
            cursor: pointer;
            font-size: 0.85rem;
        }}
        .autocomplete-item:hover {{
            background-color: #f3f4f6 !important;
        }}
        .dark .autocomplete-item:hover {{
            background-color: #374151 !important;
        }}
    </style>

    <script>
        const ALL_MODELS = {all_models};
        const ALL_FIELDS = {all_fields};

        document.addEventListener('DOMContentLoaded', function () {{
            initAutocomplete('allowed_models', ALL_MODELS, 'auto-tag-model', 'Search Django model (e.g. store.Product, Order)...');
            initAutocomplete('blocked_fields', ALL_FIELDS.map(f => ({{value: f, label: f}})), 'auto-tag-field', 'Search field name to block (e.g. password, price, ssn)...');
        }});

        function initAutocomplete(fieldName, options, tagClass, placeholder) {{
            const jsonInput = document.getElementById('id_' + fieldName);
            if (!jsonInput) return;

            jsonInput.style.display = 'none';

            let selectedValues = [];
            try {{
                selectedValues = JSON.parse(jsonInput.value || "[]");
            }} catch(e) {{
                selectedValues = [];
            }}
            if (!Array.isArray(selectedValues)) selectedValues = [];

            const container = document.createElement('div');
            container.className = 'w-full space-y-2';

            container.innerHTML = `
                <div class="relative w-full">
                    <input type="text" id="${{fieldName}}-auto-input" placeholder="${{placeholder}}"
                        class="auto-input-box w-full px-4 py-2.5 text-sm border rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none"
                        autocomplete="off" />
                </div>
                <div id="${{fieldName}}-tags" class="flex flex-wrap gap-2 pt-1"></div>
            `;

            const dropdownEl = document.createElement('div');
            dropdownEl.id = `${{fieldName}}-dropdown`;
            dropdownEl.className = 'autocomplete-dropdown-fixed custom-scrollbar';
            document.body.appendChild(dropdownEl);

            jsonInput.parentNode.insertBefore(container, jsonInput.nextSibling);

            const inputEl = document.getElementById(`${{fieldName}}-auto-input`);
            const tagsEl = document.getElementById(`${{fieldName}}-tags`);

            function positionDropdown() {{
                const rect = inputEl.getBoundingClientRect();
                dropdownEl.style.top = (rect.bottom + 4) + 'px';
                dropdownEl.style.left = rect.left + 'px';
                dropdownEl.style.width = rect.width + 'px';
            }}

            function renderTags() {{
                tagsEl.innerHTML = '';
                selectedValues.forEach(val => {{
                    const tag = document.createElement('span');
                    tag.className = `auto-tag ${{tagClass}}`;
                    tag.innerHTML = `
                        <span>${{val}}</span>
                        <span class="auto-tag-remove" onclick="removeTag('${{fieldName}}', '${{val}}')">&times;</span>
                    `;
                    tagsEl.appendChild(tag);
                }});
                jsonInput.value = JSON.stringify(selectedValues);
            }}

            window.removeTag = function(targetField, val) {{
                if (targetField === fieldName) {{
                    selectedValues = selectedValues.filter(v => v !== val);
                    renderTags();
                }}
            }};

            function addValue(val) {{
                if (!selectedValues.includes(val)) {{
                    selectedValues.push(val);
                    renderTags();
                }}
                inputEl.value = '';
                dropdownEl.style.display = 'none';
            }}

            inputEl.addEventListener('input', function() {{
                const q = this.value.trim().toLowerCase();
                if (!q) {{
                    dropdownEl.style.display = 'none';
                    return;
                }}
                const matches = options.filter(opt =>
                    opt.value.toLowerCase().includes(q) || opt.label.toLowerCase().includes(q)
                ).slice(0, 15);

                if (matches.length === 0) {{
                    dropdownEl.innerHTML = `<div class="p-3 text-xs text-gray-400 italic">No matches found. Press Enter to add "${{q}}" custom entry</div>`;
                }} else {{
                    dropdownEl.innerHTML = matches.map(opt => `
                        <div class="autocomplete-item text-gray-800 dark:text-gray-200" data-val="${{opt.value}}">
                            ${{opt.label}}
                        </div>
                    `).join('');
                }}

                positionDropdown();
                dropdownEl.style.display = 'block';

                dropdownEl.querySelectorAll('.autocomplete-item').forEach(item => {{
                    item.addEventListener('click', function() {{
                        addValue(this.getAttribute('data-val'));
                    }});
                }});
            }});

            inputEl.addEventListener('keydown', function(e) {{
                if (e.key === 'Enter') {{
                    e.preventDefault();
                    const val = this.value.trim();
                    if (val) addValue(val);
                }}
            }});

            window.addEventListener('resize', positionDropdown);
            window.addEventListener('scroll', positionDropdown, true);

            document.addEventListener('click', function(e) {{
                if (!container.contains(e.target) && !dropdownEl.contains(e.target)) {{
                    dropdownEl.style.display = 'none';
                }}
            }});

            renderTags();
        }}
    </script>
    """
    return mark_safe(html)


# ──────────────────────────────────────────────────────────────────────────────
# AgentConfig Form
# ──────────────────────────────────────────────────────────────────────────────

class AgentConfigForm(forms.ModelForm):
    class Meta:
        model = AgentConfig
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["allowed_models"].widget.attrs.update({"class": "hidden-json-input"})
        self.fields["blocked_fields"].widget.attrs.update({"class": "hidden-json-input"})
        # Attach autocomplete script cleanly to allowed_models help text
        script = _autocomplete_script_html()
        original_help = self.fields["allowed_models"].help_text or ""
        self.fields["allowed_models"].help_text = mark_safe(original_help + str(script))


# ──────────────────────────────────────────────────────────────────────────────
# AgentConfig Admin
# ──────────────────────────────────────────────────────────────────────────────

class ChatThreadInline(TabularInline):
    model = ChatThread
    fields = ("thread_id", "user", "created_at", "updated_at")
    readonly_fields = ("thread_id", "user", "created_at", "updated_at")
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = "Active Thread"
    verbose_name_plural = "Active Threads"

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("-updated_at")


@admin.register(AgentConfig)
class AgentConfigAdmin(ModelAdmin):
    form = AgentConfigForm
    list_display = (
        "name", "display_name", "status_badge", "model_display",
        "whitelisted_models_count", "tool_count", "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "display_name", "system_prompt")
    readonly_fields = (
        "created_at", "updated_at", "available_tools_panel",
        "builtin_tools_info",
    )
    prepopulated_fields = {"name": ("display_name",)}
    save_on_top = True

    fieldsets = (
        ("🤖 Identity", {
            "fields": ("name", "display_name", "is_active"),
        }),
        ("💬 Behaviour", {
            "fields": ("system_prompt",),
            "description": (
                "Use <code>{user_id}</code>, <code>{date}</code>, <code>{summary}</code> "
                "as placeholders for runtime context injection."
            ),
        }),
        ("🧠 LLM Model Settings", {
            "fields": ("model_name", "max_tokens", "summary_threshold"),
            "description": (
                "Specify OpenRouter model ID (e.g. 'google/gemini-2.5-flash'). Leave blank to use global settings."
            ),
        }),
        ("🗄️ Whitelisted Django Models (Autocomplete)", {
            "fields": ("allowed_models",),
            "description": (
                "Search and select Django ORM models allowed for this agent to access."
            ),
        }),
        ("🛡️ Blocked Field Names (Autocomplete)", {
            "fields": ("blocked_fields",),
            "description": (
                "Search and select field names or sensitive tokens to block for this agent."
            ),
        }),
        ("🔧 Built-in ORM Tools (always active)", {
            "fields": ("builtin_tools_info",),
            "description": (
                "These 4 tools are automatically included in every agent and driven by "
                "<code>allowed_models</code> or global <code>MODEL_WHITELIST</code> in settings.py."
            ),
        }),
        ("➕ Extra Custom Tools", {
            "fields": ("extra_tools", "extra_approval_tools", "available_tools_panel"),
            "description": (
                "Add custom tool names (e.g. <code>[\"send_email\", \"send_push_notification\"]</code>). "
                "Each tool must be registered with <code>@register_tool</code> in your code."
            ),
        }),
        ("📅 Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    inlines = [ChatThreadInline]

    @admin.display(description="Status", ordering="is_active")
    def status_badge(self, obj):
        if obj.is_active:
            return mark_safe('<span style="color:#10b981;font-weight:bold">● Active</span>')
        return mark_safe('<span style="color:#ef4444;font-weight:bold">● Inactive</span>')

    @admin.display(description="LLM Model")
    def model_display(self, obj):
        if obj.model_name:
            return format_html('<code style="font-size:0.85em">{}</code>', obj.model_name)
        return mark_safe('<em style="color:#888">default</em>')

    @admin.display(description="Allowed Models")
    def whitelisted_models_count(self, obj):
        count = len(obj.allowed_models or [])
        if count > 0:
            return format_html('<span style="color:#10b981;font-weight:bold">{} models</span>', count)
        return mark_safe('<em style="color:#888">all (settings)</em>')

    @admin.display(description="Tools")
    def tool_count(self, obj):
        builtin = 4
        extra = len(obj.extra_tools or [])
        total = builtin + extra
        return format_html('<span title="4 built-in + {} custom">{} total</span>', extra, total)

    def available_tools_panel(self, obj=None):
        return mark_safe(_available_tools_html())
    available_tools_panel.short_description = "Available Custom Tools"

    def builtin_tools_info(self, obj=None):
        tools = [
            ("get_model_schema", "Describe accessible model fields to the LLM"),
            ("query_records", "Filter and paginate model records"),
            ("add_record", "Create a new record (approval-gated)"),
            ("update_record", "Update a record by ID (approval-gated)"),
        ]
        rows = "".join(
            f"<tr><td style='padding:4px 10px'><code>{name}</code></td>"
            f"<td style='padding:4px 10px;color:#6b7280'>{desc}</td></tr>"
            for name, desc in tools
        )
        return mark_safe(f"<table style='border-collapse:collapse;margin-top:4px'><tbody>{rows}</tbody></table>")
    builtin_tools_info.short_description = "Built-in Tools"


class ChatMessageInline(TabularInline):
    model = ChatMessage
    fields = ("role_display", "short_text", "model_name", "created_at")
    readonly_fields = ("role_display", "short_text", "model_name", "created_at")
    extra = 0
    can_delete = False
    ordering = ("created_at",)

    @admin.display(description="Role")
    def role_display(self, obj):
        if obj.is_user:
            return mark_safe('<span style="color:#3b82f6;font-weight:bold">👤 User</span>')
        return mark_safe('<span style="color:#10b981;font-weight:bold">🤖 AI</span>')

    @admin.display(description="Message")
    def short_text(self, obj):
        return obj.text[:120] + ("…" if len(obj.text) > 120 else "")


@admin.register(ChatThread)
class ChatThreadAdmin(ModelAdmin):
    list_display = ("thread_id", "agent", "user", "message_count", "updated_at")
    list_filter = ("agent",)
    search_fields = ("thread_id", "user__username", "user__email")
    readonly_fields = ("thread_id", "agent", "user", "created_at", "updated_at")
    inlines = [ChatMessageInline]

    @admin.display(description="Messages")
    def message_count(self, obj):
        return obj.messages.count()

    def has_add_permission(self, request):
        return False


@admin.register(ChatMessage)
class ChatMessageAdmin(ModelAdmin):
    list_display = ("id", "thread_link", "role_badge", "short_text", "model_name", "created_at")
    list_filter = ("is_user", "thread__agent")
    search_fields = ("text", "thread__thread_id")
    readonly_fields = ("thread", "text", "is_user", "model_name", "created_at")

    @admin.display(description="Thread")
    def thread_link(self, obj):
        return format_html(
            '<a href="/admin/django_ai_agent/chatthread/{}/change/">{}</a>',
            obj.thread_id,
            obj.thread.thread_id[:20],
        )

    @admin.display(description="Role")
    def role_badge(self, obj):
        if obj.is_user:
            return mark_safe('<span style="color:#3b82f6;font-weight:bold">👤 User</span>')
        return mark_safe('<span style="color:#10b981;font-weight:bold">🤖 AI</span>')

    @admin.display(description="Text")
    def short_text(self, obj):
        return obj.text[:80] + ("…" if len(obj.text) > 80 else "")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
