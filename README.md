# django-langgraph-agent

![Status: Beta](https://img.shields.io/badge/status-beta-orange)

> [!WARNING]
> **Beta Release**: This project is currently in **Beta** and is **not ready for production use**. Features and APIs are subject to change.

A reusable Django package for building **streaming AI agents** powered by [LangGraph](https://github.com/langchain-ai/langgraph) and [OpenRouter](https://openrouter.ai).

Battle-tested in internal workflows at [Tathbeet](https://tathbeet.space) — a Quran memorization platform.

---


<img width="1024" height="642" alt="admin-chat-ui" src="https://github.com/user-attachments/assets/417ee3b8-b4b9-4059-9bf5-b804aad2cb3f" />

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
    "DEFAULT_MODEL": "google/gemini-3.5-flash-lite",
    "FALLBACK_MODELS": ["google/gemini-2.0-flash-001", "openai/gpt-4o-mini"],

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

## Securing the API Endpoints

The endpoints exposed by `include("django_langgraph_agent.urls")` drive the ORM
tools — they can read, create and update every whitelisted model — so they are
**protected by default**: staff only, CSRF enforced, and no client-supplied
`user_id`.

```python
DJANGO_LANGGRAPH_AGENT = {
    # "staff" (default) | "authenticated" | "public" | "myapp.perms.can_chat"
    "API_PERMISSION": "staff",

    # CSRF stays on; the bundled chat template already sends X-CSRFToken.
    "API_CSRF_EXEMPT": False,

    # Let an *unauthenticated* caller pick a user id via the request body.
    # Off by default — it allows impersonating any user.
    "TRUST_BODY_USER_ID": False,
}
```

A dotted path (or a callable) receives the request and returns a bool:

```python
# myapp/perms.py
def can_chat(request):
    return request.user.is_authenticated and request.user.has_perm("myapp.use_agent")
```

Anonymous callers get `401`, authenticated-but-unauthorised callers get `403`.
When `PERSIST_MESSAGES` is on, non-staff callers are additionally confined to
their own threads — they cannot read, post into, or delete someone else's
`thread_id`.

---

## Row-Level Scoping (Multi-Tenancy)

`MODEL_WHITELIST`, `allowed_models` and `blocked_fields` control **which models
and fields** are reachable. `QUERYSET_SCOPE` controls **which rows** — the hook
every read and update is filtered through. Telling the agent in its system
prompt to "always filter by organization" is not a control; it is a suggestion
the model can drop.

```python
def scope_to_organization(model, config):
    """model: the Django model. config: the LangGraph RunnableConfig."""
    user_id = config.get("configurable", {}).get("user_id")
    if not hasattr(model, "organization"):
        return None                      # leave this model unscoped
    if not user_id:
        return model.objects.none()      # deny outright
    org_id = User.objects.get(pk=user_id).organization_id
    return {"organization_id": org_id}   # a dict of filters, or a QuerySet


def organization_defaults(model, config):
    """Field values forced onto every add_record / update_record write."""
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id or not hasattr(model, "organization"):
        return {}
    return {"organization_id": User.objects.get(pk=user_id).organization_id}


DJANGO_LANGGRAPH_AGENT = {
    "QUERYSET_SCOPE": scope_to_organization,   # or "myapp.scopes.scope_to_organization"
    "WRITE_DEFAULTS": organization_defaults,
}
```

- `QUERYSET_SCOPE` returns a `QuerySet`, a dict of filter kwargs, or `None` to
  leave that model unscoped. Return `model.objects.none()` to deny access.
  It becomes the base queryset for `query_records`, `aggregate_model_records`
  and the lookup in `update_record`, so an out-of-scope row cannot be read or
  written.
- `WRITE_DEFAULTS` values are authoritative — they override anything the model
  supplied — and are applied *after* field validation, so concrete `<fk>_id`
  keys work even when the `fields` allowlist only lists `<fk>`.

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

The docstring is the prompt the model reads, so describe the arguments and their
units there rather than in a comment.

**Requiring approval.** A custom tool that writes data or reaches the outside
world should be gated the same way the built-in write tools are — approval is
opt-in per tool, so anything you leave out runs unattended:

```python
# code-defined agents
DjangoAgent(
    name="store_admin",
    tools=toolkit.tools + [apply_discount, send_order_confirmation],
    approval_tools=list(toolkit.approval_tools) + ["apply_discount", "send_order_confirmation"],
)
```

For agents configured in the admin, list the same names under **Extra Custom
Tools** and **Extra Approval Tools**.

**Reading the request context.** Declare a `config: RunnableConfig = None`
parameter and the agent's `RunnableConfig` is passed in — that is where
`thread_id` and `user_id` live:

```python
@register_tool
@tool
def apply_discount(product_id: int, percent: float, config: RunnableConfig = None) -> str:
    """Reduces a product's price by `percent`."""
    actor = (config or {}).get("configurable", {}).get("user_id", "anonymous")
    ...
```

A complete, runnable set of three custom tools — read-only, write-with-approval,
and a non-ORM side effect — lives in
[`example_project/store/tools.py`](example_project/store/tools.py), wired up in
`store/agents.py` and registered from `store/apps.py`.

---

## Choosing the Upstream Model Provider

Every model is reached through an OpenAI-compatible endpoint, which defaults to
OpenRouter. Two settings control where requests actually land.

**Pinning the OpenRouter route.** OpenRouter picks the upstream provider itself
unless you tell it otherwise, and its default pick is not always the cheapest —
Gemini, for instance, bills through Vertex by default while Google AI Studio is
a separate, cheaper route:

```python
DJANGO_LANGGRAPH_AGENT = {
    # Shorthand: a string or list becomes {"order": [...]}
    "OPENROUTER_PROVIDER": "google-ai-studio",

    # Or OpenRouter's full provider object
    "OPENROUTER_PROVIDER": {"order": ["google-ai-studio"], "allow_fallbacks": False},
}
```

This applies to the primary model, every fallback model, and the summarizer.

**Leaving OpenRouter entirely.** Point the package at any OpenAI-compatible
endpoint:

```python
DJANGO_LANGGRAPH_AGENT = {
    "OPENROUTER_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai",
    "OPENROUTER_API_KEY": os.environ["GOOGLE_AI_STUDIO_KEY"],
}
```

**Anything else.** `EXTRA_BODY` is merged into every request body (OpenRouter's
`transforms`, `route`, `reasoning`, …) and `MODEL_KWARGS` is passed straight
through to `ChatOpenAI`:

```python
DJANGO_LANGGRAPH_AGENT = {
    "EXTRA_BODY": {"transforms": ["middle-out"]},
    "MODEL_KWARGS": {"temperature": 0.2},
}
```

`OPENROUTER_PROVIDER` wins over a `provider` key set in `EXTRA_BODY`.

| Setting | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint |
| `OPENROUTER_PROVIDER` | `None` | Upstream route, sent as `extra_body["provider"]` |
| `EXTRA_BODY` | `{}` | Extra JSON merged into every request body |
| `MODEL_KWARGS` | `{}` | Extra `ChatOpenAI(**kwargs)` |

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

> 🔒 Every endpoint below is guarded by `API_PERMISSION` (staff-only by default)
> and expects a CSRF token on POST — see [Securing the API Endpoints](#securing-the-api-endpoints).

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

