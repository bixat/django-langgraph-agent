"""
django_ai_agent/state.py

Generic LangGraph state for all agents built with this package.

user_id and any app-specific context are intentionally omitted here;
they are injected securely via LangGraph RunnableConfig so the LLM
can never spoof them.

Custom agents can extend AgentState with additional fields:

    from django_ai_agent.state import AgentState
    from typing import Optional

    class MyAgentState(AgentState):
        room_id: Optional[int]
"""

from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    Base state for all Django AI agents.

    messages: The full chat history for the current thread.
    summary:  A compressed summary of older messages, generated automatically
              when the history exceeds SUMMARY_THRESHOLD turns.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    summary: Optional[str]
