"""
django_langgraph_agent/graph.py

Generic LangGraph agent graph factory.

Creates a compiled StateGraph with:
  - Custom tool execution with human-in-the-loop approval
  - Automatic conversation summarization to manage token usage
  - Gemini-safe message sanitization on every LLM call
  - Configurable approval-required tool set

This is the core of the package — agent-agnostic and fully configurable.
"""

import json
import logging

from langchain_core.messages import HumanMessage, RemoveMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from .conf import agent_settings
from .sanitize import sanitize_messages_for_gemini
from .state import AgentState

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Human-Readable Tool Label Builder
# ──────────────────────────────────────────────────────────────────────────────

def default_label_builder(tool_name: str, args: dict) -> str:
    """
    Generates a human-readable description of a tool call for the approval UI.
    Override by passing `label_builder` to `create_agent_graph()`.
    """
    return f"Execute `{tool_name}` with args: {json.dumps(args, ensure_ascii=False)[:120]}"


# ──────────────────────────────────────────────────────────────────────────────
# Summarization Node
# ──────────────────────────────────────────────────────────────────────────────

def _summarize_node(state: AgentState, config=None, llm=None) -> dict:
    """
    Summarizes the conversation history to reduce token usage.
    Triggered when message count exceeds SUMMARY_THRESHOLD.
    """
    summary = state.get("summary", "")
    messages = state.get("messages", [])

    if not messages:
        return {}

    if summary:
        prompt = (
            f"Previous summary:\n{summary}\n\n"
            "Extend this summary with the new messages below. "
            "Be concise. Preserve any important decisions or context. "
            "Do NOT include conversational filler, greetings, or formatting headers like '### Conversation Summary:'."
        )
    else:
        prompt = (
            "Summarize this conversation concisely. "
            "Preserve any important decisions, data queries, and context. "
            "Do NOT include conversational filler, greetings, or formatting headers like '### Conversation Summary:'."
        )

    summary_messages = messages + [HumanMessage(content=prompt)]
    response = llm.invoke(summary_messages)  # Never pass config to summarizer

    clean_summary = str(getattr(response, "content", "") or "").strip()
    for prefix in ["### Conversation Summary:", "Conversation Summary:", "Summary:"]:
        if clean_summary.startswith(prefix):
            clean_summary = clean_summary[len(prefix):].strip()

    # Keep only the last 2 messages (most recent exchange), plus the newest
    # HumanMessage. The graph routes agent → execute_tools → summarize → agent,
    # so on a tool turn the last two messages are the AIMessage holding the tool
    # call and its ToolMessage — dropping messages[:-2] would delete the very
    # question being answered, and the next agent pass would reply with a
    # generic greeting instead of an answer.
    newest_question_id = next(
        (
            m.id
            for m in reversed(messages)
            if isinstance(m, HumanMessage) and getattr(m, "id", None)
        ),
        None,
    )
    delete_messages = [
        RemoveMessage(id=m.id)
        for m in messages[:-2]
        if getattr(m, "id", None) and m.id != newest_question_id
    ]

    return {"summary": clean_summary, "messages": delete_messages}


# ──────────────────────────────────────────────────────────────────────────────
# Graph Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_agent_graph(
    llm,
    tools: list,
    state_modifier,
    approval_tools: set | None = None,
    summary_threshold: int | None = None,
    label_builder=None,
    state_schema=None,
):
    """
    Builds and returns an uncompiled LangGraph StateGraph.

    Args:
        llm:              A LangChain chat model (e.g. from build_llm()).
        tools:            List of LangChain tools the agent can call.
        state_modifier:   Callable(state, config) → list[BaseMessage].
                          Injects the system prompt and any context messages.
        approval_tools:   Set of tool names that require user approval before
                          execution. Defaults to DJANGO_LANGGRAPH_AGENT["APPROVAL_REQUIRED_TOOLS"].
        summary_threshold: Message count that triggers summarization.
                          Defaults to DJANGO_LANGGRAPH_AGENT["SUMMARY_THRESHOLD"].
        label_builder:    Callable(tool_name, args) → str for human-readable labels.
        state_schema:     Custom TypedDict state class. Defaults to AgentState.

    Returns:
        An uncompiled StateGraph. Call `.compile(checkpointer=...)` on it.
    """
    from .llm import build_summarizer_llm

    if approval_tools is None:
        approval_tools = set(agent_settings.APPROVAL_REQUIRED_TOOLS)

    if summary_threshold is None:
        summary_threshold = agent_settings.SUMMARY_THRESHOLD

    if label_builder is None:
        label_builder = default_label_builder

    if state_schema is None:
        state_schema = AgentState

    llm_with_tools = llm.bind_tools(tools, parallel_tool_calls=True)
    tools_by_name = {t.name: t for t in tools}
    summarizer_llm = build_summarizer_llm()

    # ── Agent Node ──────────────────────────────────────────────────────────
    def agent_node(state, config):
        messages = state_modifier(state, config)
        messages = sanitize_messages_for_gemini(messages)
        response = llm_with_tools.invoke(messages, config)

        finish_reason = (response.response_metadata or {}).get("finish_reason")
        if finish_reason == "length":
            thread_id = config.get("configurable", {}).get("thread_id", "?")
            logger.warning(
                "LLM response truncated (finish_reason=length) for thread %s", thread_id
            )
        return {"messages": [response]}

    # ── Tool Execution Node (with human-in-the-loop) ────────────────────────
    def execute_tools_node(state, config):
        """
        Intercepts AI tool calls requiring approval.

        - Auto-execute tool calls → run immediately.
        - Approval-required tool calls → pause via interrupt(), send payload to client.

        On resume, the client sends decisions: {tool_call_id: "approve" | "deny"}.
        Every tool_call gets exactly one ToolMessage response to maintain Gemini
        message sequence integrity.
        """
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", None) or []
        if not tool_calls:
            return {}

        needs_approval = [tc for tc in tool_calls if tc["name"] in approval_tools]

        decisions = {}
        if needs_approval:
            approval_payload = [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": tc["args"],
                    "human_label": label_builder(tc["name"], tc["args"]),
                }
                for tc in needs_approval
            ]
            resume_value = interrupt({"tool_calls": approval_payload})
            decisions = (
                resume_value.get("decisions", {}) if isinstance(resume_value, dict) else {}
            )

        tool_messages = []
        for tc in tool_calls:
            name = tc["name"]
            tool_id = tc["id"]
            args = tc["args"]

            if name in approval_tools and decisions.get(tool_id, "deny") != "approve":
                # User denied this action — inject a descriptive ToolMessage
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=tool_id,
                        content=(
                            f"USER DENIED: The user chose to DENY the action '{name}'. "
                            "This is NOT a technical error. "
                            "You MUST inform the user their action was cancelled. "
                            "Do NOT retry. Do NOT apologise for a failure."
                        ),
                        name=name,
                    )
                )
            else:
                try:
                    tool = tools_by_name[name]
                    result = tool.invoke(args, config)
                    content = (
                        result
                        if isinstance(result, str)
                        else json.dumps(result, ensure_ascii=False)
                    )
                except Exception as exc:
                    logger.warning("Tool execution error '%s': %s", name, exc)
                    content = f"Tool execution failed: {exc}"

                tool_messages.append(
                    ToolMessage(tool_call_id=tool_id, content=content, name=name)
                )

        return {"messages": tool_messages}

    # ── Conditional Routing Functions ────────────────────────────────────────

    def should_summarize(state: AgentState) -> str:
        """Triggers conversation summarization when threshold is met."""
        messages = state.get("messages", [])
        if len(messages) > summary_threshold:
            return "summarize"
        return "continue"

    def router(state: AgentState) -> str:
        """Routes to execute_tools if last message has tool calls, else END."""
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", None)
        if tool_calls:
            return "execute_tools"
        return END

    def summarize_node_func(state, config=None):
        return _summarize_node(state, config, summarizer_llm)

    # ── Graph Assembly ───────────────────────────────────────────────────────
    workflow = StateGraph(state_schema)

    # Nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("summarize", summarize_node_func)

    # Entry point
    workflow.set_entry_point("agent")

    # Routing
    workflow.add_conditional_edges("agent", router, ["execute_tools", END])
    workflow.add_conditional_edges(
        "execute_tools", should_summarize, {"summarize": "summarize", "continue": "agent"}
    )
    workflow.add_edge("summarize", "agent")

    return workflow
