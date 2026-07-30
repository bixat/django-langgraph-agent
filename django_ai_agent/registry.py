"""
django_ai_agent/registry.py

Global tool registry for django-langgraph-agent.

Allows tools to be registered by name so they can be:
  - Selected in the Django Admin AgentConfig form (by name)
  - Looked up at runtime when building the agent graph

Usage
-----
    # In your app (e.g. myapp/tools.py), decorate tools with @register_tool:

    from django_ai_agent import register_tool
    from langchain_core.tools import tool

    @register_tool          # <-- registers it
    @tool                   # <-- makes it a LangChain tool
    def search_products(query: str) -> str:
        "Search products by name."
        from myapp.models import Product
        results = Product.objects.filter(name__icontains=query)
        return str(list(results.values("id", "name", "price")))
"""

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Global registry: tool_name (str) → LangChain tool callable
_REGISTRY: dict[str, object] = {}


def register_tool(tool_fn):
    """
    Decorator that registers a LangChain tool in the global registry.
    """
    name = getattr(tool_fn, "name", None) or getattr(tool_fn, "__name__", str(tool_fn))
    if name in _REGISTRY:
        logger.warning(
            "django-langgraph-agent: Tool '%s' is already registered — overwriting.", name
        )
    _REGISTRY[name] = tool_fn
    logger.debug("Registered tool: %s", name)
    return tool_fn


def unregister_tool(name_or_fn):
    """
    Removes a registered tool from the global registry.
    """
    tool_name = getattr(name_or_fn, "name", None) or getattr(name_or_fn, "__name__", str(name_or_fn))
    if tool_name in _REGISTRY:
        del _REGISTRY[tool_name]


def get_tool(name: str):
    """
    Returns a registered tool by name.
    Raises KeyError if not found.
    """
    if name not in _REGISTRY:
        available = list(_REGISTRY.keys())
        raise KeyError(
            f"Tool '{name}' is not registered. "
            f"Available tools: {available}. "
            "Make sure you imported the module that registers it."
        )
    return _REGISTRY[name]


def get_tools(names: list[str]) -> list:
    """
    Returns a list of registered tools by name.
    Raises KeyError if any name is not found.
    """
    return [get_tool(name) for name in names]


def list_tools() -> dict[str, str]:
    """
    Returns a dict of {name: docstring} for all registered tools.
    Used by the Django Admin to show available tool choices.
    """
    result = {}
    for name, fn in _REGISTRY.items():
        doc = getattr(fn, "description", None) or getattr(fn, "__doc__", "") or ""
        result[name] = doc.strip().split("\n")[0]  # first line only
    return result


def _register_builtin_tools():
    """
    Auto-registers all built-in ORM tools so they appear in the admin
    without the developer needing to call register_tool manually.
    """
    try:
        from django_ai_agent.tools.django_orm import (
            get_model_schema,
            query_records,
            aggregate_model_records,
            add_record,
            update_record,
        )
        for t in [get_model_schema, query_records, aggregate_model_records, add_record, update_record]:
            register_tool(t)
    except Exception as exc:
        logger.warning("Could not register built-in ORM tools: %s", exc)
