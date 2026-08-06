"""
tests/test_admin_and_api.py

Tests for AgentConfig DB model, tool registration, and API endpoints.
"""

import json
import pytest
from django.test import override_settings
from langchain_core.tools import tool

from django_langgraph_agent import DjangoAgent, register_tool, unregister_tool
from django_langgraph_agent.models import AgentConfig, ChatThread, ChatMessage


@tool
def send_test_email(to: str, subject: str, body: str) -> str:
    """Send a test email."""
    return f"Email sent to {to}: {subject}"


@pytest.mark.django_db
def test_tool_registration():
    """register_tool adds functions to the registry."""
    from django_langgraph_agent.registry import get_tool, list_tools, unregister_tool

    register_tool(send_test_email)
    tools = list_tools()
    assert "send_test_email" in tools
    assert get_tool("send_test_email") == send_test_email

    unregister_tool("send_test_email")
    assert "send_test_email" not in list_tools()


@pytest.mark.django_db
def test_agent_config_to_django_agent():
    """AgentConfig model correctly instantiates a DjangoAgent."""
    register_tool(send_test_email)

    config = AgentConfig.objects.create(
        name="test-admin-agent",
        display_name="Test Admin Agent",
        system_prompt="You are a test agent.",
        model_name="google/gemini-3.5-flash-lite",
        extra_tools=["send_test_email"],
        extra_approval_tools=["send_test_email"],
    )

    agent = config.to_django_agent()
    assert isinstance(agent, DjangoAgent)
    assert agent.name == "test-admin-agent"
    assert agent.model_name == "google/gemini-3.5-flash-lite"
    assert "send_test_email" in agent.approval_tools

    unregister_tool("send_test_email")


@pytest.mark.django_db
def test_list_agents_api_endpoint(client):
    """GET /api/agent/ returns active agents."""
    AgentConfig.objects.create(
        name="agent-one", display_name="Agent One", system_prompt="One", is_active=True
    )
    AgentConfig.objects.create(
        name="agent-two", display_name="Agent Two", system_prompt="Two", is_active=False
    )

    response = client.get("/api/agent/")
    assert response.status_code == 200
    data = response.json()
    assert len(data["agents"]) == 1
    assert data["agents"][0]["name"] == "agent-one"


@pytest.mark.django_db
def test_agent_config_allowed_models_and_blocked_fields():
    """AgentConfig passes allowed_models and blocked_fields down to DjangoAgent and system prompt."""
    config = AgentConfig.objects.create(
        name="restricted-agent",
        display_name="Restricted Agent",
        system_prompt="Help",
        allowed_models=["store.Order"],
        blocked_fields=["internal_notes"],
    )
    agent = config.to_django_agent()
    assert agent.allowed_models == ["store.Order"]
    assert agent.blocked_fields == ["internal_notes"]

    messages = agent._state_modifier({}, {"configurable": {"user_id": 1}})
    sys_prompt = messages[0].content
    assert "Order" in sys_prompt


@pytest.mark.django_db
def test_delete_thread_view(client):
    """POST /api/agent/chat/delete/ deletes ChatThread and its messages."""
    agent = AgentConfig.objects.create(name="test-del", display_name="Test Del", system_prompt="Test")
    thread = ChatThread.objects.create(thread_id="thread-del-123", agent=agent)
    ChatMessage.objects.create(thread=thread, text="Hello", is_user=True)

    response = client.post(
        "/api/agent/chat/delete/",
        data=json.dumps({"thread_id": "thread-del-123"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"
    assert not ChatThread.objects.filter(thread_id="thread-del-123").exists()


@pytest.mark.django_db
def test_chat_page_view_requires_login(client):
    """GET /api/agent/chat/ui/ redirects to admin login if not authenticated."""
    response = client.get("/api/agent/chat/ui/")
    # staff_member_required redirects unauthenticated users to admin login
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_chat_page_view_staff_can_access(client, django_user_model):
    """GET /api/agent/chat/ui/ renders standalone chat template for staff users."""
    AgentConfig.objects.create(
        name="test-agent", display_name="Test Agent", system_prompt="Test", is_active=True
    )
    user = django_user_model.objects.create_user(
        username="admin_tester", password="secret", is_staff=True
    )
    client.force_login(user)
    response = client.get("/api/agent/chat/ui/")
    assert response.status_code == 200
    assert "Test Agent" in response.content.decode()
    assert "django_langgraph_agent/chat.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_get_threads_view(client):
    """GET /api/agent/chat/threads/?agent=<name> returns JSON thread list."""
    agent = AgentConfig.objects.create(
        name="test-agent", display_name="Test Agent", system_prompt="Test", is_active=True
    )
    thread = ChatThread.objects.create(thread_id="thread-xyz-123", agent=agent)
    ChatMessage.objects.create(thread=thread, text="Hello world from user", is_user=True)

    with override_settings(DJANGO_LANGGRAPH_AGENT={"PERSIST_MESSAGES": True}):
        response = client.get("/api/agent/chat/threads/?agent=test-agent")
        assert response.status_code == 200
        data = response.json()
        assert data["persist"] is True
        assert len(data["threads"]) == 1
        assert data["threads"][0]["id"] == "thread-xyz-123"
        assert "Hello world" in data["threads"][0]["title"]
