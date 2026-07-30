# django-langgraph-agent

A reusable Django package for building **streaming AI agents** powered by [LangGraph](https://github.com/langchain-ai/langgraph) and [OpenRouter](https://openrouter.ai).

Battle-tested in production at [Tathbeet](https://tathbeet.space) — a Quran memorization platform serving thousands of users.

---

## Features

- ⚙️ **Admin-Managed Agents** — create and customize agents from the Django Admin UI without code changes
- 🔌 **Zero-Boilerplate API** — built-in SSE chat & approval endpoints ready out-of-the-box (`include("django_ai_agent.urls")`)
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
    "django_ai_agent",
]
```

### 2. Add Built-in URLs (`urls.py`)

```python
from django.urls import path, include

urlpatterns = [
    # Adds endpoints: GET /api/agent/, POST /api/agent/chat/, POST /api/agent/chat/approve/
    path("api/agent/", include("django_ai_agent.urls")),
]
```

### 3. Configure `settings.py`

```python
DJANGO_AI_AGENT = {
    "OPENROUTER_API_KEY": env("OPENROUTER_API_KEY"),

    # LLM configuration (OpenRouter model IDs)
    "DEFAULT_MODEL": "google/gemini-2.5-flash-preview",
    "FALLBACK_MODELS": ["google/gemini-2.5-flash", "deepseek/deepseek-chat"],

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

Navigate to `/admin/django_ai_agent/agentconfig/add/`:
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
from django_ai_agent import register_tool

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

### 2. Chat SSE Endpoint (`POST /api/agent/chat/`)
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

### 3. Tool Approval SSE Endpoint (`POST /api/agent/chat/approve/`)
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

## Code-Based Agent Definition (Alternative)

If you prefer defining agents directly in Python code instead of Django Admin:

```python
from django_ai_agent import DjangoAgent, stream_agent
from django_ai_agent.tools import DjangoORMToolkit

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

Open [http://localhost:8000/chat/](http://localhost:8000/chat/) for the dark-mode streaming test UI.

---

## License

MIT
