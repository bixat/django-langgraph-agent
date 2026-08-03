"""
django_langgraph_agent management command: setup_agent_db

Creates the LangGraph checkpoint tables in the database.
Run this after adding django_langgraph_agent to INSTALLED_APPS and running migrations.

Usage:
    python manage.py setup_agent_db
    python manage.py setup_agent_db --agent my_agent_name
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates LangGraph checkpoint tables for django-langgraph-agent"

    def add_arguments(self, parser):
        parser.add_argument(
            "--agent",
            type=str,
            default="default",
            help="Agent name to set up tables for (default: 'default')",
        )

    def handle(self, *args, **options):
        agent_name = options["agent"]
        self.stdout.write(f"Setting up LangGraph checkpoint tables for agent '{agent_name}'...")

        from django_langgraph_agent.checkpointer import setup_checkpointer

        try:
            setup_checkpointer(agent_name)
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ LangGraph checkpoint tables are ready for agent '{agent_name}'."
                )
            )
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Failed to set up checkpoint tables: {exc}"))
            raise
