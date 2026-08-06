# django-langgraph-agent

![Status: Beta](https://img.shields.io/badge/status-beta-orange)

> [!WARNING]
> **Beta Release**: This project is currently in **Beta** and is **not ready for production use**. Features and APIs are subject to change.

A reusable Django package for building **streaming AI agents** powered by [LangGraph](https://github.com/langchain-ai/langgraph) and [OpenRouter](https://openrouter.ai).

Battle-tested in internal workflows at [Tathbeet](https://tathbeet.space) — a Quran memorization platform.

---

## Features

- ⚙️ **Admin-Managed Agents** — create and customize agents from the Django Admin UI without code changes
- 🔌 **Zero-Boilerplate API & UI** — built-in SSE chat endpoints & admin-integrated Chat UI (`include("django_langgraph_agent.urls")`)
- 🎨 **Unfold / Django Admin Integration** — built-in chat UI embeds natively inside Django Admin / Unfold layout
- 📱 **Responsive Mobile Drawer** — conversations sidebar collapses into a slide-out drawer on small screens
- 🔄 **Dynamic Agent Switcher** — switch between active AI agents instantly without a full page refresh
- 🧰 **Auto-Included ORM Tools** — safe CRUD tools automatically attached and configured via `MODEL_WHITELIST` in `settings.py`
- 🎯 **Tool Registry (`@register_tool`)** — easily add custom tools (e.g. notifications, emails, external integrations)
- ⚡ **Streaming SSE** — yields real-time `token`, `tool_approval`, `done`, and `error` events
- 🛡️ **Human-in-the-Loop** — pause agents on sensitive actions (e.g. create/update), resume upon user confirmation
- 🧠 **Auto Summarization** — automatically compresses long conversations to preserve token limits
- 🔄 **Multi-Model Fallback** — primary model + fallback chain resilient to provider rate limits
- 🗄️ **WSGI-Safe Checkpointer** — zero idle connection leaks with PostgreSQL NullPool, SQLite, or MemorySaver
- 🧹 **Gemini-Safe Turn Sanitizer** — prevents strict turn-order errors when using Google AI Studio / Gemini models

---

## Installation

```bash
pip install django-langgraph-agent

# Optional: PostgreSQL checkpointer support
pip install django-langgraph-agent[postgres]
```

---

## Quick Start (Zero-Boilerplate Setup)

### 1. Add to `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    ...
    "django_langgraph_agent",
]
```

### 2. Add Built-in URLs (`urls.py`)

```python
from django.contrib import admin
from django.urls import path, include
from django_langgraph_agent.api_views import admin_chat_view

urlpatterns = [
    # Admin Panel (Unfold theme compatible)
    path("admin/", admin.site.urls),

    # Built-in Admin AI Chat Workspace
    path("admin/ai-chat/", admin.site.admin_view(admin_chat_view), name="admin_ai_chat"),

    # All API endpoints & built-in Chat UI (GET /api/agent/chat/ui/)
    path("api/agent/", include("django_langgraph_agent.urls")),
]
```

### 3. Configure `settings.py`

```python
DJANGO_LANGGRAPH_AGENT = {
    "OPENROUTER_API_KEY": env("OPENROUTER_API_KEY"),

    # LLM configuration (OpenRouter model IDs)
    "DEFAULT_MODEL": "google/gemini-2.5-flash-preview",
    "FALLBACK_MODELS": ["google/gemini-2.5-flash", "deepseek/deepseek-chat"],

    # Enables conversation thread history
    "PERSIST_MESSAGES": True,

    # Django ORM whitelist — controls accessible models and fields
    "MODEL_WHITELIST": {
        "Product": {
            "app_label": "store",
            "display_name": "Store Product",
            "fields": ["id", "name", "price", "category", "stock", "is_active"],  # allowlist
        },
        "Order": {
            "app_label": "store",
            "display_name": "Customer Order",
            "exclude_fields": ["payment_reference", "internal_notes"],  # blocklist
        },
    },
}
```

### 4. Run Migrations & DB Setup

```bash
python manage.py migrate
python manage.py setup_agent_db
```

### 5. Create an Agent in Django Admin

Navigate to `/admin/django_langgraph_agent/agentconfig/add/`:
- **Name**: `support`
- **Display Name**: `Customer Support Agent`
- **System Prompt**: `You are a helpful store assistant. Use {user_id} and {date} context.`

> 💡 **Built-in ORM tools** (`get_model_schema`, `query_records`, `add_record`, `update_record`) are automatically attached to every agent based on your `MODEL_WHITELIST`.

---

## Adding Custom Tools (`@register_tool`)

To add external integrations (push notifications, emails, third-party APIs):

```python
# myapp/tools.py
from langchain_core.tools import tool
from django_langgraph_agent import register_tool

@register_tool
@tool
def send_push_notification(user_id: int, title: str, message: str) -> str:
    """Send a push notification to a user's device."""
    # ... your notification code ...
    return f"Notification sent to user #{user_id}"
```

Import your tools module in your app's `AppConfig.ready()` so registration runs on startup:

```python
# myapp/apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        import myapp.tools  # noqa: F401
```

Now `send_push_notification` will appear in the Django Admin for selection under **Extra Custom Tools**.

---

## Django Unfold Admin Theme Integration

If you use [django-unfold](https://github.com/unfoldadmin/django-unfold) for your Django Admin panel, you can add the AI Chat workspace and Agent Configuration links directly to your `UNFOLD["SIDEBAR"]` navigation in `settings.py`:

```python
UNFOLD = {
    "SITE_TITLE": "My App Dashboard",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "🤖 AI Chat",
                "separator": True,
                "items": [
                    {
                        "title": "Open AI Chat",
                        "icon": "smart_toy",
                        "link": lambda request: "/admin/ai-chat/",
                    },
                ],
            },
            {
                "title": "⚙️ Agent Configuration",
                "separator": True,
                "items": [
                    {
                        "title": "Agent Configurations",
                        "icon": "tune",
                        "link": lambda request: "/admin/django_langgraph_agent/agentconfig/",
                    },
                    {
                        "title": "Chat Threads",
                        "icon": "chat",
                        "link": lambda request: "/admin/django_langgraph_agent/chatthread/",
                    },
                    {
                        "title": "Chat Messages Log",
                        "icon": "chat_bubble",
                        "link": lambda request: "/admin/django_langgraph_agent/chatmessage/",
                    },
                ],
            },
        ],
    },
}
```

---

## API Endpoints Reference

### 1. List Agents (`GET /api/agent/`)
Returns active agents available for chat.
```json
{
  "agents": [
    { "name": "support", "display_name": "Customer Support Agent" }
  ]
}
```

### 2. Built-in Admin Chat UI (`GET /api/agent/chat/ui/` or `/admin/ai-chat/`)
Renders the **admin-protected chat page** integrated into the Django Admin layout.

```
/api/agent/chat/ui/              → opens chat with first active agent
/api/agent/chat/ui/?agent=name  → opens a specific agent
/api/agent/chat/ui/?agent=name&thread_id=xyz  → opens a specific conversation
```

### 3. Agent Threads API (`GET /api/agent/chat/threads/`)
Returns JSON thread list for dynamic agent switching without full page reloads.
```json
{
  "persist": true,
  "threads": [
    { "id": "thread-1", "title": "Check available products…", "date": "Aug 06, 14:30" }
  ]
}
```

### 4. Chat SSE Endpoint (`POST /api/agent/chat/`)
Start a conversation turn.
```json
{
  "agent": "support",
  "message": "What products are available under $50?",
  "thread_id": "user-session-123"
}
```

**SSE Events emitted:**
- `event: token` — `{"text": "...", "model_name": "..."}`
- `event: tool_approval` — `{"tool_calls": [{"id": "tc_1", "name": "add_record", "human_label": "Create record"}]}`
- `event: done` — `{"model_name": "..."}`
- `event: error` — `{"message": "..."}`

### 5. Tool Approval SSE Endpoint (`POST /api/agent/chat/approve/`)
Resume execution after the user approves or denies a tool call.
```json
{
  "agent": "support",
  "thread_id": "user-session-123",
  "decisions": {
    "tc_1": "approve"  // or "deny"
  }
}
```

---

## Customising the Chat UI Template

The built-in chat page (`/api/agent/chat/ui/` / `/admin/ai-chat/`) renders the template:

```
django_langgraph_agent/templates/django_langgraph_agent/chat.html
```

You can **override it** exactly like you override Django admin templates — just create the same path inside your own app's `templates/` directory:

```
myapp/
  templates/
    django_langgraph_agent/
      chat.html   ← your custom override
```

Make sure your app is listed **before** `django_langgraph_agent` in `INSTALLED_APPS`, and that `APP_DIRS = True` (or your `TEMPLATES` loader includes your app's `templates/` directory). Django's template engine will find your file first.

---

## Code-Based Agent Definition (Alternative)

If you prefer defining agents directly in Python code instead of Django Admin:

```python
from django_langgraph_agent import DjangoAgent, stream_agent
from django_langgraph_agent.tools import DjangoORMToolkit

toolkit = DjangoORMToolkit(include_write=True)

my_agent = DjangoAgent(
    name="my_agent",
    system_prompt="You are a helpful assistant.",
    tools=toolkit.tools,
    approval_tools=toolkit.approval_tools,
)

# Stream response in a custom view
def my_view(request):
    gen = stream_agent(my_agent, message="Hello", thread_id="t1", user_id=request.user.id)
    return StreamingHttpResponse(gen, content_type="text/event-stream")
```

---

## Running the Example Project

```bash
cd django-langgraph-agent/
pip install -e ".[test]"
export OPENROUTER_API_KEY=sk-or-...

PYTHONPATH=. python3 example_project/manage.py migrate
PYTHONPATH=. python3 example_project/manage.py setup_agent_db
PYTHONPATH=. python3 example_project/manage.py runserver
```

Open [http://localhost:8000/admin/ai-chat/](http://localhost:8000/admin/ai-chat/) for the streaming chat UI inside the Unfold Django Admin panel.

---

## License

MIT

