"""
example_project/store/agents.py

Example agent definitions for the store app.

Two agents are defined here:
  1. store_agent     — customer-facing agent (read-only, no write tools)
  2. store_admin_agent — admin agent with full CRUD + approval flow
"""

from django_langgraph_agent import DjangoAgent
from django_langgraph_agent.tools import DjangoORMToolkit

# ──────────────────────────────────────────────────────────────────────────────
# Customer-Facing Agent (read-only)
# ──────────────────────────────────────────────────────────────────────────────

_read_toolkit = DjangoORMToolkit(include_write=False)

store_agent = DjangoAgent(
    name="store",
    system_prompt=(
        "You are a helpful store assistant for our online shop. "
        "You can look up products, check availability, and help customers find what they need. "
        "Be friendly, concise, and helpful. "
        "Format prices with a $ sign. "
        "Never reveal internal fields like cost_price or payment_reference."
    ),
    tools=_read_toolkit.tools,
)


# ──────────────────────────────────────────────────────────────────────────────
# Admin Agent (full CRUD with approval)
# ──────────────────────────────────────────────────────────────────────────────

_admin_toolkit = DjangoORMToolkit(include_write=True)

store_admin_agent = DjangoAgent(
    name="store_admin",
    system_prompt=(
        "You are the store admin AI assistant. "
        "You can query, create, and update products and orders. "
        "⚠️ Always confirm with the user before making any changes. "
        "Be precise about what data you're modifying."
    ),
    tools=_admin_toolkit.tools,
    # Write tools require explicit user approval
    approval_tools=_admin_toolkit.approval_tools,
)


# ──────────────────────────────────────────────────────────────────────────────
# Advanced: Agent with custom system prompt (callable form)
# Useful when you need user-specific context, language, date injection, etc.
# ──────────────────────────────────────────────────────────────────────────────

def _dynamic_state_modifier(state: dict, config: dict):
    """
    Example of a callable system prompt that injects runtime context.
    """
    from django.utils import timezone
    from langchain_core.messages import SystemMessage

    messages = state.get("messages", [])
    summary = state.get("summary", "")
    user_id = config.get("configurable", {}).get("user_id")
    current_date = timezone.now().strftime("%Y-%m-%d %H:%M")

    system = (
        f"You are a personalized store assistant.\n"
        f"Current date/time: {current_date}\n"
        f"User ID: {user_id or 'anonymous'}\n"
        "Help the user find products and manage their orders."
    )

    if summary:
        system += f"\n\nConversation so far:\n{summary}"

    return [SystemMessage(content=system)] + messages


personalized_agent = DjangoAgent(
    name="store_personalized",
    system_prompt=_dynamic_state_modifier,  # callable, not string
    tools=_read_toolkit.tools,
)
