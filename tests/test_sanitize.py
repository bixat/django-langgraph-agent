"""
tests/test_sanitize.py

Tests for the Gemini message sanitizer.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


def make_ai_with_tool_calls(tool_calls):
    return AIMessage(content="", tool_calls=tool_calls)


def make_tool_msg(tool_call_id, name="tool"):
    return ToolMessage(content="result", tool_call_id=tool_call_id, name=name)


def test_valid_sequence_unchanged():
    """A correct sequence is returned unchanged."""
    from django_langgraph_agent.sanitize import sanitize_messages_for_gemini

    ai_msg = make_ai_with_tool_calls([{"id": "1", "name": "get_data", "args": {}}])
    tool_msg = make_tool_msg("1", "get_data")
    human_msg = HumanMessage(content="hello")

    result = sanitize_messages_for_gemini([human_msg, ai_msg, tool_msg])
    assert len(result) == 3


def test_missing_tool_message_auto_filled():
    """Missing ToolMessages are auto-filled with synthetic placeholders."""
    from django_langgraph_agent.sanitize import sanitize_messages_for_gemini

    ai_msg = make_ai_with_tool_calls([{"id": "abc", "name": "my_tool", "args": {}}])
    # No ToolMessage follows — should be auto-filled
    result = sanitize_messages_for_gemini([ai_msg])

    assert len(result) == 2  # AIMessage + synthetic ToolMessage
    assert isinstance(result[1], ToolMessage)
    assert result[1].tool_call_id == "abc"


def test_orphan_tool_message_stripped():
    """Orphan ToolMessages not preceded by matching AIMessage are removed."""
    from django_langgraph_agent.sanitize import sanitize_messages_for_gemini

    orphan = make_tool_msg("orphan-id")
    human = HumanMessage(content="hi")
    result = sanitize_messages_for_gemini([orphan, human])

    assert len(result) == 1
    assert result[0] == human


def test_empty_ai_message_stripped():
    """Empty AIMessages (no content, no tool_calls) are removed."""
    from django_langgraph_agent.sanitize import sanitize_messages_for_gemini

    empty_ai = AIMessage(content="")
    human = HumanMessage(content="hello")
    result = sanitize_messages_for_gemini([empty_ai, human])

    assert len(result) == 1
    assert result[0] == human


def test_system_and_human_always_kept():
    """SystemMessage and HumanMessage always pass through."""
    from django_langgraph_agent.sanitize import sanitize_messages_for_gemini

    sys_msg = SystemMessage(content="You are an assistant.")
    human_msg = HumanMessage(content="Hello!")
    result = sanitize_messages_for_gemini([sys_msg, human_msg])

    assert len(result) == 2


def test_multiple_tool_calls_all_filled():
    """When an AI has multiple tool calls, all get ToolMessages."""
    from django_langgraph_agent.sanitize import sanitize_messages_for_gemini

    ai_msg = make_ai_with_tool_calls([
        {"id": "tc1", "name": "tool_a", "args": {}},
        {"id": "tc2", "name": "tool_b", "args": {}},
    ])
    # Only provide one ToolMessage — tc2 should be auto-filled
    tool_msg = make_tool_msg("tc1", "tool_a")
    result = sanitize_messages_for_gemini([ai_msg, tool_msg])

    # Should have: AIMessage + ToolMessage for tc1 + synthetic for tc2
    assert len(result) == 3
    tool_ids = {m.tool_call_id for m in result if isinstance(m, ToolMessage)}
    assert "tc1" in tool_ids
    assert "tc2" in tool_ids
