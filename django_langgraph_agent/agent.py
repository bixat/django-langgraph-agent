"""
django_langgraph_agent/agent.py

The main DjangoAgent interface for django-langgraph-agent.
"""

import logging
from typing import Callable, Union

from langchain_core.messages import BaseMessage, SystemMessage

from .conf import agent_settings

logger = logging.getLogger(__name__)


class DjangoAgent:
    """
    A fully configured, reusable AI agent for Django applications.
    """

    def __init__(
        self,
        name: str,
        system_prompt,
        tools: list,
        approval_tools: set | None = None,
        max_tokens: int | None = None,
        summary_threshold: int | None = None,
        label_builder: Callable | None = None,
        state_schema=None,
        model_name: str | None = None,
        allowed_models: list | None = None,
        blocked_fields: list | None = None,
        llm=None,
    ):
        self.name = name
        self.system_prompt_arg = system_prompt
        self.tools = tools
        self.max_tokens = max_tokens
        self.summary_threshold = summary_threshold
        self.label_builder = label_builder
        self.state_schema = state_schema
        self.model_name = model_name
        self.allowed_models = allowed_models or []
        self.blocked_fields = blocked_fields or []
        self._custom_llm = llm

        if approval_tools is not None:
            self.approval_tools = set(approval_tools)
        else:
            self.approval_tools = set(
                getattr(agent_settings, "APPROVAL_REQUIRED_TOOLS", [])
            )

        self._compiled_graph = None

    def _state_modifier(self, state: dict, config: dict) -> list[BaseMessage]:
        existing_messages = state.get("messages", [])
        if callable(self.system_prompt_arg):
            sys_msgs = self.system_prompt_arg(state, config)
            return sys_msgs + existing_messages

        prompt_str = str(self.system_prompt_arg)

        configurable = config.get("configurable", {})
        user_id = configurable.get("user_id")

        if user_id:
            prompt_str = prompt_str.replace("{user_id}", str(user_id))

        from datetime import datetime
        prompt_str = prompt_str.replace("{date}", datetime.now().strftime("%Y-%m-%d"))

        from .tools.django_orm import get_whitelisted_models_summary
        models_info = get_whitelisted_models_summary(self.allowed_models)
        if models_info:
            prompt_str += (
                f"\n\nAccessible Database Models for this Agent:\n{models_info}\n"
                "Use query_records to list records or aggregate_model_records to calculate counts, sums, averages, mins, or maxes."
            )

        summary = state.get("summary", "")
        if summary:
            prompt_str += (
                "\n\n[INTERNAL MEMORY - CONVERSATION SUMMARY (FOR YOUR CONTEXT ONLY, DO NOT REPEAT OR OUTPUT THIS SUMMARY TO THE USER)]\n"
                f"{summary}\n"
                "[END INTERNAL MEMORY]"
            )

        prompt_str += (
            "\n\n[COMMUNICATION DIRECTIVE]\n"
            "1. Always address the user directly in second person ('Here are your orders...', 'How can I help you today?').\n"
            "2. NEVER speak about the user in third person (e.g. do NOT say 'User requested...', 'The user wants...', 'Customer asked for...').\n"
            "3. NEVER repeat, quote, or output the internal conversation summary or memory notes to the user.\n"
            "4. Communicate in a warm, natural, and human-friendly tone.\n"
            "5. NEVER use technical backend jargon like 'CRUD', 'Model Schemas', 'Query Records', 'Aggregate Records', or 'Databases' when responding to the user."
        )

        return [SystemMessage(content=prompt_str)] + existing_messages

    def get_graph(self):
        if self._compiled_graph is not None:
            return self._compiled_graph

        from .checkpointer import get_checkpointer, setup_checkpointer
        from .graph import create_agent_graph
        from .llm import build_llm

        llm = self._custom_llm or build_llm(
            model=self.model_name,
            title=agent_settings.SITE_TITLE,
            max_tokens=self.max_tokens,
        )

        graph = create_agent_graph(
            llm=llm,
            tools=self.tools,
            state_modifier=self._state_modifier,
            approval_tools=self.approval_tools,
            summary_threshold=self.summary_threshold,
            label_builder=self.label_builder,
            state_schema=self.state_schema,
        )

        checkpointer = get_checkpointer(self.name)
        setup_checkpointer(self.name)

        self._compiled_graph = graph.compile(checkpointer=checkpointer)
        logger.info("DjangoAgent '%s' graph compiled and ready.", self.name)
        return self._compiled_graph

    def thread_id(self, raw_id: str) -> str:
        return f"{self.name}:{raw_id}"

    def get_human_label(self, tool_name: str, args: dict) -> str:
        if self.label_builder:
            try:
                return self.label_builder(tool_name, args)
            except Exception as exc:
                logger.warning("label_builder raised an error for '%s': %s", tool_name, exc)
        return f"Tool: {tool_name} with args: {args}"

    def __repr__(self):
        tool_names = [getattr(t, "name", str(t)) for t in self.tools]
        return (
            f"<DjangoAgent name='{self.name}' "
            f"tools={tool_names} approval_tools={len(self.approval_tools)}>"
        )
