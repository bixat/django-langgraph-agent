"""
tests/test_api_security.py

Tests for the built-in API endpoint guard: permission policy, CSRF, the
body user_id fallback, and per-thread ownership.

Regression coverage for issue #2 (endpoints shipped unauthenticated and
csrf_exempt).
"""

import json

import pytest
from django.test import Client, override_settings

from django_langgraph_agent.models import AgentConfig, ChatThread, ChatMessage

ENDPOINTS = [
    ("get", "/api/agent/"),
    ("get", "/api/agent/chat/threads/?agent=test-agent"),
]


@pytest.fixture
def agent(db):
    return AgentConfig.objects.create(
        name="test-agent", display_name="Test Agent", system_prompt="Test", is_active=True
    )


# ── Default policy: staff only ───────────────────────────────────────────────

@pytest.mark.django_db
@pytest.mark.parametrize("method,url", ENDPOINTS)
def test_anonymous_is_rejected(client, agent, method, url):
    """Anonymous callers get 401 on every built-in endpoint by default."""
    response = getattr(client, method)(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_anonymous_cannot_post_chat(client, agent):
    """The SSE chat endpoint rejects anonymous callers before any agent work."""
    response = client.post(
        "/api/agent/chat/",
        data=json.dumps({"agent": "test-agent", "message": "hi", "thread_id": "t1"}),
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_anonymous_cannot_approve_or_delete(client, agent):
    """approve/ and delete/ are guarded too."""
    for url in ("/api/agent/chat/approve/", "/api/agent/chat/delete/"):
        response = client.post(url, data="{}", content_type="application/json")
        assert response.status_code == 401, url


@pytest.mark.django_db
def test_non_staff_is_rejected_by_default(user_client, agent):
    """A logged-in non-staff user gets 403 under the default 'staff' policy."""
    response = user_client.get("/api/agent/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_is_allowed(staff_client, agent):
    response = staff_client.get("/api/agent/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_staff_reaches_chat_view_body_validation(staff_client, agent):
    """A staff caller gets past the guard (400 from body validation, not 401/403)."""
    response = staff_client.post(
        "/api/agent/chat/", data="not json", content_type="application/json"
    )
    assert response.status_code == 400


# ── Configurable policies ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_authenticated_policy_allows_non_staff(user_client, agent):
    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": "authenticated"}):
        assert user_client.get("/api/agent/").status_code == 200


@pytest.mark.django_db
def test_authenticated_policy_still_rejects_anonymous(client, agent):
    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": "authenticated"}):
        assert client.get("/api/agent/").status_code == 401


@pytest.mark.django_db
def test_public_policy_opts_out(client, agent):
    """'public' restores the old open behaviour, but only as an explicit opt-in."""
    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": "public"}):
        assert client.get("/api/agent/").status_code == 200


@pytest.mark.django_db
def test_callable_policy(client, user_client, agent):
    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": lambda request: True}):
        assert client.get("/api/agent/").status_code == 200
    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": lambda request: False}):
        assert user_client.get("/api/agent/").status_code == 403


DOTTED_POLICY = "django_langgraph_agent.api_views._is_staff"


@pytest.mark.django_db
def test_dotted_path_policy_denies(user_client, agent):
    """A dotted path to callable(request) -> bool is imported and applied."""
    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": DOTTED_POLICY}):
        assert user_client.get("/api/agent/").status_code == 403


@pytest.mark.django_db
def test_dotted_path_policy_allows(staff_client, agent):
    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": DOTTED_POLICY}):
        assert staff_client.get("/api/agent/").status_code == 200


# ── CSRF ─────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_views_are_not_csrf_exempt_by_default():
    """
    The csrf_exempt flag must not survive on the URL callback — CsrfViewMiddleware
    reads it there, and a wraps() chain that copies __dict__ silently disables
    CSRF for every later decorator layer.
    """
    from django_langgraph_agent.api_views import chat_view, approve_view, delete_thread_view

    for view in (chat_view, approve_view, delete_thread_view):
        assert getattr(view, "csrf_exempt", False) is False


@pytest.mark.django_db
def test_csrf_is_enforced_for_staff_post(agent, django_user_model):
    """A staff session without a CSRF token is rejected."""
    user = django_user_model.objects.create_user(
        username="csrf_tester", password="secret", is_staff=True
    )
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(user)

    response = csrf_client.post(
        "/api/agent/chat/delete/",
        data=json.dumps({"thread_id": "nope"}),
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_csrf_exempt_setting_opts_out(agent, django_user_model):
    user = django_user_model.objects.create_user(
        username="csrf_tester2", password="secret", is_staff=True
    )
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(user)

    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_CSRF_EXEMPT": True}):
        response = csrf_client.post(
            "/api/agent/chat/delete/",
            data=json.dumps({"thread_id": "nope"}),
            content_type="application/json",
        )
        assert response.status_code == 200


# ── user_id impersonation ────────────────────────────────────────────────────

def test_body_user_id_is_ignored_by_default(rf):
    from django_langgraph_agent.api_views import _get_user_id

    request = rf.post("/api/agent/chat/")
    request.user = type("Anon", (), {"is_authenticated": False})()
    assert _get_user_id(request, {"user_id": 42}) is None


def test_body_user_id_is_opt_in(rf):
    from django_langgraph_agent.api_views import _get_user_id

    request = rf.post("/api/agent/chat/")
    request.user = type("Anon", (), {"is_authenticated": False})()
    with override_settings(DJANGO_LANGGRAPH_AGENT={"TRUST_BODY_USER_ID": True}):
        assert _get_user_id(request, {"user_id": 42}) == 42


@pytest.mark.django_db
def test_authenticated_user_id_wins_over_body(rf, django_user_model):
    from django_langgraph_agent.api_views import _get_user_id

    user = django_user_model.objects.create_user(username="real_user", password="secret")
    request = rf.post("/api/agent/chat/")
    request.user = user
    with override_settings(DJANGO_LANGGRAPH_AGENT={"TRUST_BODY_USER_ID": True}):
        assert _get_user_id(request, {"user_id": 999}) == user.pk


# ── Per-thread ownership ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_non_staff_cannot_delete_another_users_thread(user_client, agent, django_user_model):
    owner = django_user_model.objects.create_user(username="thread_owner", password="secret")
    ChatThread.objects.create(thread_id="someone-elses", agent=agent, user=owner)

    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": "authenticated"}):
        response = user_client.post(
            "/api/agent/chat/delete/",
            data=json.dumps({"thread_id": "someone-elses"}),
            content_type="application/json",
        )
    assert response.status_code == 403
    assert ChatThread.objects.filter(thread_id="someone-elses").exists()


@pytest.mark.django_db
def test_non_staff_cannot_post_into_another_users_thread(user_client, agent, django_user_model):
    owner = django_user_model.objects.create_user(username="thread_owner2", password="secret")
    ChatThread.objects.create(thread_id="private-thread", agent=agent, user=owner)

    with override_settings(DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": "authenticated"}):
        response = user_client.post(
            "/api/agent/chat/",
            data=json.dumps({"agent": "test-agent", "message": "hi", "thread_id": "private-thread"}),
            content_type="application/json",
        )
    assert response.status_code == 403


@pytest.mark.django_db
def test_non_staff_thread_list_is_scoped_to_own_threads(user_client, agent, django_user_model):
    owner = django_user_model.objects.create_user(username="thread_owner3", password="secret")
    other = ChatThread.objects.create(thread_id="other-thread", agent=agent, user=owner)
    ChatMessage.objects.create(thread=other, text="secret question", is_user=True)
    mine = ChatThread.objects.create(thread_id="my-thread", agent=agent, user=user_client.user)
    ChatMessage.objects.create(thread=mine, text="my question", is_user=True)

    with override_settings(
        DJANGO_LANGGRAPH_AGENT={"API_PERMISSION": "authenticated", "PERSIST_MESSAGES": True}
    ):
        response = user_client.get("/api/agent/chat/threads/?agent=test-agent")

    assert response.status_code == 200
    ids = [t["id"] for t in response.json()["threads"]]
    assert ids == ["my-thread"]
