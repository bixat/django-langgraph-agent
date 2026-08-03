"""
tests/test_agent.py

Tests for the DjangoAgent class.
"""

import pytest
from django.test import override_settings
from langchain_core.tools import tool
from unittest.mock import MagicMock, patch


AGENT_SETTINGS = {
    "OPENROUTER_API_KEY": "test-key",
    "DEFAULT_MODEL": "test/model",
    "FALLBACK_MODELS": [],
    "MAX_TOKENS": 500,
    "SUMMARY_THRESHOLD": 4,
    "SITE_URL": "http://test.local",
    "SITE_TITLE": "Test Agent",
    "APPROVAL_REQUIRED_TOOLS": [],
    "MODEL_WHITELIST": {},
    "BLOCKED_FIELD_SUBSTRINGS": ["password"],
}


@tool
def hello_tool(name: str) -> str:
    """Says hello to a person."""
    return f"Hello, {name}!"


def test_agent_repr():
    """DjangoAgent repr is informative."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=AGENT_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent import DjangoAgent

        agent = DjangoAgent(
            name="test_agent",
            system_prompt="You are a test agent.",
            tools=[hello_tool],
        )
        rep = repr(agent)
        assert "test_agent" in rep
        assert "hello_tool" in rep


def test_agent_thread_id_namespaced():
    """Thread IDs are namespaced with the agent name."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=AGENT_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent import DjangoAgent

        agent = DjangoAgent(
            name="my_agent",
            system_prompt="Test.",
            tools=[],
        )
        assert agent.thread_id("thread-123") == "my_agent:thread-123"


def test_callable_system_prompt():
    """Callable system_prompt is used as-is as state_modifier."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=AGENT_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent import DjangoAgent
        from langchain_core.messages import SystemMessage

        def my_modifier(state, config):
            return [SystemMessage(content="Custom!")]

        agent = DjangoAgent(
            name="custom_agent",
            system_prompt=my_modifier,
            tools=[],
        )
        # The state modifier should be exactly the callable we passed
        result = agent._state_modifier({"messages": []}, {})
        assert len(result) == 1
        assert result[0].content == "Custom!"


def test_string_system_prompt_includes_summary():
    """String system_prompt includes conversation summary when available."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=AGENT_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent import DjangoAgent

        agent = DjangoAgent(
            name="sum_agent",
            system_prompt="You are a test agent.",
            tools=[],
        )
        result = agent._state_modifier(
            {"messages": [], "summary": "User asked about products."},
            {},
        )
        # Should have SystemMessage containing the summary
        content = result[0].content
        assert "User asked about products." in content


def test_approval_tools_defaults_from_settings():
    """approval_tools defaults to DJANGO_LANGGRAPH_AGENT['APPROVAL_REQUIRED_TOOLS']."""
    with override_settings(DJANGO_LANGGRAPH_AGENT={
        **AGENT_SETTINGS,
        "APPROVAL_REQUIRED_TOOLS": ["add_record", "update_record"],
    }):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent import DjangoAgent

        agent = DjangoAgent(
            name="approval_agent",
            system_prompt="Test.",
            tools=[],
        )
        assert "add_record" in agent.approval_tools
        assert "update_record" in agent.approval_tools


def test_approval_tools_can_be_overridden():
    """approval_tools can be explicitly overridden at agent construction."""
    with override_settings(DJANGO_LANGGRAPH_AGENT={
        **AGENT_SETTINGS,
        "APPROVAL_REQUIRED_TOOLS": ["add_record"],
    }):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent import DjangoAgent

        agent = DjangoAgent(
            name="override_agent",
            system_prompt="Test.",
            tools=[],
            approval_tools={"my_custom_tool"},
        )
        assert "my_custom_tool" in agent.approval_tools
        assert "add_record" not in agent.approval_tools
