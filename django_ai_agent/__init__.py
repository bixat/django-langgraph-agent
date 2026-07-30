"""
django_ai_agent — Django AI Agent Package

A reusable Django package for building streaming AI agents powered by
LangGraph and OpenRouter.
"""

default_app_config = "django_ai_agent.apps.DjangoAIAgentConfig"

from .agent import DjangoAgent
from .conf import agent_settings
from .registry import register_tool, unregister_tool
from .streaming import resume_agent, stream_agent
from .tools import DjangoORMToolkit

__all__ = [
    "DjangoAgent",
    "register_tool",
    "unregister_tool",
    "agent_settings",
    "stream_agent",
    "resume_agent",
    "DjangoORMToolkit",
]

__version__ = "0.1.0"
