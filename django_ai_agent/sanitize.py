"""
django_ai_agent/sanitize.py

Sanitizes LangChain message sequences to comply with Google Gemini's
strict turn rules. This is applied automatically by the agent graph
before every LLM invocation — it cannot be disabled because disabling
it causes silent, hard-to-debug failures with the Gemini provider.

Rules enforced:
  1. Every AIMessage with tool_calls MUST be immediately followed by
     matching ToolMessages for ALL tool_call_ids in its list.
  2. Missing ToolMessages are auto-filled with a synthetic placeholder
     so Gemini never sees a broken sequence.
  3. Orphan ToolMessages (not preceded by a matching AIMessage) are removed.
  4. Empty AIMessages (no content, no tool_calls) are stripped out.
"""


def sanitize_messages_for_gemini(messages: list) -> list:
    """
    Returns a cleaned message list safe for submission to the Gemini provider.
    """
    from langchain_core.messages import ToolMessage, AIMessage

    if not messages:
        return []

    new_messages = []
    i = 0
    n = len(messages)

    while i < n:
        msg = messages[i]

        # ── Case 1: AIMessage with tool_calls ────────────────────────────────
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls = msg.tool_calls
            expected_ids: set = set()
            tc_map: dict = {}

            for tc in tool_calls:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "tool")
                if tc_id:
                    expected_ids.add(tc_id)
                    tc_map[tc_id] = tc_name

            new_messages.append(msg)
            i += 1

            # Collect subsequent ToolMessages that match expected tool_call_ids
            found_tool_messages = []
            while i < n:
                next_msg = messages[i]
                is_tool_msg = (
                    getattr(next_msg, "type", "") == "tool" or isinstance(next_msg, ToolMessage)
                )
                if is_tool_msg:
                    tc_id = getattr(next_msg, "tool_call_id", None)
                    if tc_id in expected_ids:
                        found_tool_messages.append(next_msg)
                        expected_ids.discard(tc_id)
                    i += 1
                else:
                    break

            new_messages.extend(found_tool_messages)

            # Auto-fill synthetic ToolMessages for any missing tool_call_ids
            for missing_id in expected_ids:
                tool_name = tc_map.get(missing_id, "tool")
                new_messages.append(
                    ToolMessage(
                        content="[Tool execution completed or cancelled]",
                        tool_call_id=missing_id,
                        name=tool_name,
                    )
                )

        # ── Case 2: Orphan ToolMessage — strip it ────────────────────────────
        elif getattr(msg, "type", "") == "tool" or isinstance(msg, ToolMessage):
            i += 1

        # ── Case 3: Empty AIMessage — strip it ───────────────────────────────
        elif getattr(msg, "type", "") == "ai" or isinstance(msg, AIMessage):
            content = getattr(msg, "content", "")
            has_content = isinstance(content, str) and content.strip()
            has_tool_calls = bool(getattr(msg, "tool_calls", None))
            if not has_content and not has_tool_calls:
                i += 1
                continue
            new_messages.append(msg)
            i += 1

        # ── Case 4: SystemMessage, HumanMessage — always keep ────────────────
        else:
            new_messages.append(msg)
            i += 1

    return new_messages
