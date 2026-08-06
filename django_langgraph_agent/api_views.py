"""
django_langgraph_agent/api_views.py

Built-in API views for agent SSE chat endpoints and Admin Chat Interface.
"""

import json
import logging

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .conf import agent_settings
from .streaming import resume_agent, stream_agent

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Agent Instance Cache
# Keyed by (AgentConfig.pk, AgentConfig.updated_at.isoformat())
# Automatically invalidates when admin saves a change.
# ──────────────────────────────────────────────────────────────────────────────
_AGENT_CACHE: dict = {}


def _get_or_build_agent(agent_config):
    """
    Returns a cached DjangoAgent for this config, rebuilding if config changed.
    """
    cache_key = (agent_config.pk, agent_config.updated_at.isoformat())
    if cache_key not in _AGENT_CACHE:
        old_keys = [k for k in _AGENT_CACHE if k[0] == agent_config.pk]
        for k in old_keys:
            del _AGENT_CACHE[k]
        _AGENT_CACHE[cache_key] = agent_config.to_django_agent()
        logger.info(
            "Built DjangoAgent '%s' from DB config (pk=%s, updated=%s)",
            agent_config.name, agent_config.pk, agent_config.updated_at,
        )
    return _AGENT_CACHE[cache_key]


def _resolve_agent(agent_name: str):
    """
    Loads AgentConfig from DB by name. Returns (agent_config, error_response).
    """
    from .models import AgentConfig
    try:
        config = AgentConfig.objects.get(name=agent_name, is_active=True)
        return config, None
    except AgentConfig.DoesNotExist:
        return None, JsonResponse(
            {"error": f"Agent '{agent_name}' not found or is inactive."},
            status=404,
        )


def _get_user_id(request, body: dict) -> int | None:
    """
    Resolves user_id from the request.
    Uses request.user if authenticated, else falls back to body["user_id"].
    """
    if hasattr(request, "user") and request.user.is_authenticated:
        return request.user.pk
    return body.get("user_id")


def _persist_message(agent_config, thread_id: str, text: str, is_user: bool, model_name: str = "", user_id=None):
    """
    Optionally persists a message if DJANGO_AI_AGENT['PERSIST_MESSAGES'] is True.
    """
    if not getattr(agent_settings, "PERSIST_MESSAGES", False):
        return
    try:
        from .models import ChatThread, ChatMessage
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user = User.objects.filter(pk=user_id).first() if user_id else None
        thread, _ = ChatThread.objects.get_or_create(
            thread_id=thread_id,
            defaults={"agent": agent_config, "user": user},
        )
        ChatMessage.objects.create(
            thread=thread,
            text=text,
            is_user=is_user,
            model_name=model_name or "",
        )
        thread.save(update_fields=["updated_at"])
    except Exception as exc:
        logger.warning("Failed to persist message: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Admin Chat UI View
# ──────────────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def admin_chat_view(request):
    """
    Renders the rich admin chat page where admins can switch between active agents,
    select conversation threads, and stream responses with tool approvals.
    """
    from .models import AgentConfig, ChatThread, ChatMessage

    context = admin.site.each_context(request)

    agents = AgentConfig.objects.filter(is_active=True)
    if not agents.exists():
        context.update({
            "title": "AI Assistant",
            "agents": [],
            "error": "No active agents found. Create one in the Agent Configurations admin.",
        })
        return render(request, "admin/django_langgraph_agent/chat.html", context)

    agent_slug = request.GET.get("agent", "").strip()
    current_agent = agents.filter(name=agent_slug).first() or agents.first()

    current_thread_id = request.GET.get("thread_id")
    if current_thread_id == "new":
        import time
        new_id = f"thread-{int(time.time())}"
        from django.shortcuts import redirect
        return redirect(f"{request.path}?agent={current_agent.name}&thread_id={new_id}")

    thread_qs = ChatThread.objects.filter(agent=current_agent).order_by("-updated_at")[:30]

    if not current_thread_id and thread_qs.exists():
        current_thread_id = thread_qs.first().thread_id
    elif not current_thread_id:
        import time
        current_thread_id = f"thread-{int(time.time())}"

    thread_list = []
    for t in thread_qs:
        first_user_msg = ChatMessage.objects.filter(thread=t, is_user=True).order_by("created_at").first()
        title = (first_user_msg.text[:30] + "...") if first_user_msg else t.thread_id
        thread_list.append({
            "id": t.thread_id,
            "title": title,
            "start_time": t.created_at,
        })

    chat_history = []
    if current_thread_id:
        active_thread = ChatThread.objects.filter(thread_id=current_thread_id).first()
        if active_thread:
            chat_history = ChatMessage.objects.filter(thread=active_thread).order_by("created_at")

    context.update({
        "title": f"AI Assistant — {current_agent.display_name}",
        "agents": agents,
        "current_agent": current_agent,
        "threads": thread_list,
        "current_thread_id": current_thread_id,
        "chat_history": chat_history,
    })

    return render(request, "admin/django_langgraph_agent/chat.html", context)


# ──────────────────────────────────────────────────────────────────────────────
# Chat Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def chat_view(request):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    agent_name = body.get("agent", "").strip()
    message = body.get("message", "").strip()
    thread_id = body.get("thread_id", "").strip()

    if not agent_name:
        return JsonResponse({"error": "'agent' is required."}, status=400)
    if not message:
        return JsonResponse({"error": "'message' is required."}, status=400)
    if not thread_id:
        return JsonResponse({"error": "'thread_id' is required."}, status=400)

    agent_config, err = _resolve_agent(agent_name)
    if err:
        return err

    user_id = _get_user_id(request, body)
    agent = _get_or_build_agent(agent_config)

    _persist_message(agent_config, thread_id, message, is_user=True, user_id=user_id)

    _captured = {"text": "", "model": ""}

    def on_token(text: str):
        _captured["text"] += text

    def on_done(full_text: str, extra: dict):
        _captured["model"] = extra.get("model_name", "")
        _persist_message(
            agent_config, thread_id, full_text,
            is_user=False, model_name=_captured["model"], user_id=user_id,
        )

    gen = stream_agent(
        agent=agent,
        message=message,
        thread_id=thread_id,
        user_id=user_id,
        on_token=on_token,
        on_done=on_done,
    )

    return StreamingHttpResponse(
        gen,
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Approval Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def approve_view(request):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    agent_name = body.get("agent", "").strip()
    thread_id = body.get("thread_id", "").strip()
    decisions = body.get("decisions", {})

    if not agent_name:
        return JsonResponse({"error": "'agent' is required."}, status=400)
    if not thread_id:
        return JsonResponse({"error": "'thread_id' is required."}, status=400)
    if not isinstance(decisions, dict):
        return JsonResponse({"error": "'decisions' must be an object."}, status=400)

    agent_config, err = _resolve_agent(agent_name)
    if err:
        return err

    user_id = _get_user_id(request, body)
    agent = _get_or_build_agent(agent_config)

    def on_done(full_text: str, extra: dict):
        if full_text:
            _persist_message(
                agent_config, thread_id, full_text,
                is_user=False, model_name=extra.get("model_name", ""), user_id=user_id,
            )

    gen = resume_agent(
        agent=agent,
        thread_id=thread_id,
        decisions=decisions,
        user_id=user_id,
        on_done=on_done,
    )

    return StreamingHttpResponse(
        gen,
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Delete Thread Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def delete_thread_view(request):
    """
    Deletes a conversation thread and all its messages from the database and checkpointer.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    thread_id = body.get("thread_id") or request.GET.get("thread_id") or ""
    thread_id = str(thread_id).strip()

    if not thread_id:
        return JsonResponse({"error": "'thread_id' is required."}, status=400)

    from .models import ChatThread
    deleted_count, _ = ChatThread.objects.filter(thread_id=thread_id).delete()

    return JsonResponse({
        "status": "deleted",
        "thread_id": thread_id,
        "deleted": deleted_count > 0,
    })


# ──────────────────────────────────────────────────────────────────────────────
# Threads API (used by agent switcher — no page reload)
# ──────────────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def get_threads_view(request):
    """
    Returns JSON list of conversation threads for a given agent.
    Used by the chat UI to switch agents without a full page reload.

    GET /api/agent/chat/threads/?agent=<name>
    Response: {"threads": [{"id": str, "title": str, "date": str}, ...]}
    """
    from .models import AgentConfig, ChatThread, ChatMessage
    from .conf import agent_settings

    agent_name = request.GET.get("agent", "").strip()
    if not agent_name:
        return JsonResponse({"error": "'agent' param required"}, status=400)

    agent_config = AgentConfig.objects.filter(name=agent_name, is_active=True).first()
    if not agent_config:
        return JsonResponse({"threads": []})

    persist = getattr(agent_settings, "PERSIST_MESSAGES", False)
    if not persist:
        return JsonResponse({"threads": [], "persist": False})

    threads = []
    for t in ChatThread.objects.filter(agent=agent_config).order_by("-updated_at")[:30]:
        first_msg = ChatMessage.objects.filter(thread=t, is_user=True).order_by("created_at").first()
        title = (first_msg.text[:35] + "\u2026") if first_msg else t.thread_id
        threads.append({
            "id": t.thread_id,
            "title": title,
            "date": t.created_at.strftime("%b %d, %H:%M"),
        })
    return JsonResponse({"threads": threads, "persist": True})


# ──────────────────────────────────────────────────────────────────────────────
# Admin-Protected Chat UI View
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required(login_url="/admin/login/")
@require_http_methods(["GET"])
def chat_page_view(request):
    """
    Built-in admin-protected chat page.
    Requires staff login. Renders inside the Django Admin panel (with Unfold theme support).
    """
    from .models import AgentConfig, ChatThread, ChatMessage
    from .conf import agent_settings

    context = admin.site.each_context(request)

    agents = AgentConfig.objects.filter(is_active=True)
    if not agents.exists():
        context.update({
            "title": "AI Chat",
            "agents": [],
            "error": "No active agents found. Create one in the Agent Configurations admin.",
            "site_title": getattr(agent_settings, "SITE_TITLE", "AI Chat"),
        })
        return render(request, "django_langgraph_agent/chat.html", context)

    agent_slug = request.GET.get("agent", "").strip()
    current_agent = agents.filter(name=agent_slug).first() or agents.first()

    current_thread_id = request.GET.get("thread_id", "").strip()
    if current_thread_id == "new":
        import time
        new_id = f"thread-{int(time.time())}"
        return redirect(f"{request.path}?agent={current_agent.name}&thread_id={new_id}")

    persist_messages = getattr(agent_settings, "PERSIST_MESSAGES", False)

    thread_list = []
    chat_history = []
    if persist_messages:
        thread_qs = ChatThread.objects.filter(agent=current_agent).order_by("-updated_at")[:30]

        if not current_thread_id and thread_qs.exists():
            current_thread_id = thread_qs.first().thread_id

        for t in thread_qs:
            first_user_msg = ChatMessage.objects.filter(thread=t, is_user=True).order_by("created_at").first()
            title = (first_user_msg.text[:35] + "…") if first_user_msg else t.thread_id
            thread_list.append({
                "id": t.thread_id,
                "title": title,
                "start_time": t.created_at,
            })

        if current_thread_id:
            active_thread = ChatThread.objects.filter(thread_id=current_thread_id).first()
            if active_thread:
                chat_history = ChatMessage.objects.filter(thread=active_thread).order_by("created_at")

    if not current_thread_id:
        import time
        current_thread_id = f"thread-{int(time.time())}"

    context.update({
        "title": f"AI Chat — {current_agent.display_name}",
        "agents": agents,
        "current_agent": current_agent,
        "threads": thread_list,
        "current_thread_id": current_thread_id,
        "chat_history": chat_history,
        "persist_messages": persist_messages,
        "site_title": getattr(agent_settings, "SITE_TITLE", "AI Chat"),
    })

    return render(request, "django_langgraph_agent/chat.html", context)


admin_chat_view = chat_page_view



# ──────────────────────────────────────────────────────────────────────────────
# Agent Discovery Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def list_agents_view(request):
    from .models import AgentConfig
    agents = AgentConfig.objects.filter(is_active=True).values("name", "display_name")
    return JsonResponse({"agents": list(agents)})
