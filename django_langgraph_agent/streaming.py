"""
django_langgraph_agent/streaming.py

Streaming SSE generator functions for django-langgraph-agent.

Event Protocol
--------------
- event: token
  data: {"text": "...", "model_name": "..."}

- event: tool_approval
  data: {"tool_calls": [{"id": "...", "name": "...", "human_label": "..."}]}

- event: done
  data: {"model_name": "..."}

- event: error
  data: {"message": "..."}
"""

import json
import logging
from typing import Callable, Generator

from langchain_core.messages import AIMessage, ToolMessage

from .conf import agent_settings

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """Format a dictionary into a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_agent(
    agent,
    message: str,
    thread_id: str,
    user_id=None,
    extra_config: dict | None = None,
    on_token: Callable[[str], None] | None = None,
    on_approval: Callable[[dict], None] | None = None,
    on_done: Callable[[str, dict], None] | None = None,
) -> Generator[str, None, None]:
    """
    Streams an AI agent response as Server-Sent Events.
    """
    full_ai_message = ""
    detected_model_name = getattr(agent, "model_name", None) or getattr(agent_settings, "DEFAULT_MODEL", "")

    try:
        graph = agent.get_graph()
        namespaced_thread_id = agent.thread_id(thread_id)

        configurable = {
            "thread_id": namespaced_thread_id,
            "agent_name": getattr(agent, "name", "agent"),
            "allowed_models": getattr(agent, "allowed_models", []),
            "blocked_fields": getattr(agent, "blocked_fields", []),
        }
        if user_id is not None:
            configurable["user_id"] = user_id
        if extra_config:
            configurable.update(extra_config)

        config = {"configurable": configurable}

        for event_type, event_data in graph.stream(
            {"messages": [("user", message)]},
            config=config,
            stream_mode=["messages", "values"],
        ):
            if event_type == "messages":
                chunk, metadata = event_data
                
                # Prevent internal summarizer LLM outputs from streaming to the user
                if metadata.get("langgraph_node") == "summarize":
                    continue

                model_name = (
                    metadata.get("ls_model_name")
                    or metadata.get("model_name")
                    or getattr(agent, "model_name", None)
                    or getattr(agent_settings, "DEFAULT_MODEL", "")
                )
                if model_name:
                    detected_model_name = model_name

                if isinstance(chunk, AIMessage) and chunk.content:
                    text_content = (
                        chunk.content
                        if isinstance(chunk.content, str)
                        else str(chunk.content)
                    )
                    full_ai_message += text_content

                    if on_token:
                        on_token(text_content)

                    yield _sse(
                        "token",
                        {"text": text_content, "model_name": detected_model_name},
                    )

            elif event_type == "values":
                # Check for human-in-the-loop interrupt
                state = graph.get_state(config)
                if state.next and "execute_tools" in state.next:
                    for task in state.tasks:
                        for interrupt_item in task.interrupts:
                            payload = interrupt_item.value
                            if on_approval:
                                on_approval(payload)

                            yield _sse("tool_approval", payload)
                            return

        yield _sse("done", {"model_name": detected_model_name})

        if on_done:
            on_done(full_ai_message, {"model_name": detected_model_name})

    except Exception as exc:
        logger.exception("Error in stream_agent: %s", exc)
        yield _sse("error", {"message": str(exc)})


def stream_approval_resume(
    agent,
    thread_id: str,
    decisions: dict,
    user_id=None,
    extra_config: dict | None = None,
    on_token: Callable[[str], None] | None = None,
    on_done: Callable[[str, dict], None] | None = None,
) -> Generator[str, None, None]:
    """
    Resumes an agent turn after human approval/denial of tool calls.
    Executes approved tool calls and feeds real execution results back to the LLM.
    """
    full_ai_message = ""
    detected_model_name = getattr(agent, "model_name", None) or getattr(agent_settings, "DEFAULT_MODEL", "")

    try:
        graph = agent.get_graph()
        namespaced_thread_id = agent.thread_id(thread_id)

        configurable = {
            "thread_id": namespaced_thread_id,
            "agent_name": getattr(agent, "name", "agent"),
            "allowed_models": getattr(agent, "allowed_models", []),
            "blocked_fields": getattr(agent, "blocked_fields", []),
        }
        if user_id is not None:
            configurable["user_id"] = user_id
        if extra_config:
            configurable.update(extra_config)

        config = {"configurable": configurable}

        current_state = graph.get_state(config)
        if not current_state or not current_state.values.get("messages"):
            yield _sse("error", {"message": f"No active state found for thread '{thread_id}'."})
            return

        last_ai_msg = current_state.values["messages"][-1]
        if not isinstance(last_ai_msg, AIMessage) or not last_ai_msg.tool_calls:
            yield _sse("error", {"message": "No pending tool calls to approve."})
            return

        tool_messages = []
        for tc in last_ai_msg.tool_calls:
            decision = decisions.get(tc["id"], "deny")
            if decision == "approve":
                # Find matching tool by name in agent.tools
                tool_fn = next((t for t in agent.tools if getattr(t, "name", str(t)) == tc["name"]), None)
                if tool_fn:
                    try:
                        result = tool_fn.invoke(tc.get("args", {}), config)
                        tool_content = str(result)
                    except Exception as exc:
                        tool_content = json.dumps({"error": f"Tool execution error: {exc}"})
                else:
                    tool_content = json.dumps({"status": "approved"})

                tool_messages.append(
                    ToolMessage(
                        content=tool_content,
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    )
                )
            else:
                tool_messages.append(
                    ToolMessage(
                        content=json.dumps({"status": "denied", "reason": "User denied tool execution"}),
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    )
                )

        graph.update_state(config, {"messages": tool_messages}, as_node="execute_tools")

        for event_type, event_data in graph.stream(
            None,
            config=config,
            stream_mode=["messages", "values"],
        ):
            if event_type == "messages":
                chunk, metadata = event_data

                # Prevent internal summarizer LLM outputs from streaming to the user
                if metadata.get("langgraph_node") == "summarize":
                    continue

                model_name = (
                    metadata.get("ls_model_name")
                    or metadata.get("model_name")
                    or getattr(agent, "model_name", None)
                    or getattr(agent_settings, "DEFAULT_MODEL", "")
                )
                if model_name:
                    detected_model_name = model_name

                if isinstance(chunk, AIMessage) and chunk.content:
                    text_content = (
                        chunk.content
                        if isinstance(chunk.content, str)
                        else str(chunk.content)
                    )
                    full_ai_message += text_content

                    if on_token:
                        on_token(text_content)

                    yield _sse(
                        "token",
                        {"text": text_content, "model_name": detected_model_name},
                    )

        yield _sse("done", {"model_name": detected_model_name})

        if on_done:
            on_done(full_ai_message, {"model_name": detected_model_name})

    except Exception as exc:
        logger.exception("Error in resume_agent: %s", exc)
        yield _sse("error", {"message": str(exc)})


resume_agent = stream_approval_resume
