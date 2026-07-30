"""
django_ai_agent/checkpointer.py

Auto-detecting LangGraph checkpointer singleton.

Selects the appropriate backend based on the Django DATABASES['default'] engine:
  - PostgreSQL → NullPool-backed PostgresSaver (one connection per call,
                 zero idle connections — safe for multi-worker WSGI)
  - SQLite     → SqliteSaver with a shared connection (dev / testing only)
  - Other      → in-memory MemorySaver (fallback / CI)

One checkpointer instance is created per agent name, so multiple agents
can share a Django project without their states colliding.

# ─── Why NullPool for PostgreSQL? ────────────────────────────────────────────
# In a WSGI environment (e.g. Gunicorn), Python globals are PER-PROCESS.
# Each worker gets its own pool. With 3 workers × pool_size=20 that is 60
# LangGraph connections alone, easily exceeding typical DB connection limits.
#
# NullPool opens exactly 1 connection per LangGraph operation and closes it
# immediately when done — zero idle connections between requests.
# The ~5 ms reconnect overhead is negligible compared to LLM latency.
# ─────────────────────────────────────────────────────────────────────────────
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Registry: agent_name → checkpointer instance
_checkpointer_registry: dict = {}


def get_checkpointer(agent_name: str = "default"):
    """
    Returns a process-level checkpointer singleton keyed by `agent_name`.

    Thread IDs are namespaced with the agent name internally (see streaming.py),
    so multiple agents can safely share the same underlying DB tables.
    """
    global _checkpointer_registry

    if agent_name in _checkpointer_registry:
        return _checkpointer_registry[agent_name]

    db_settings = settings.DATABASES["default"]
    engine = db_settings.get("ENGINE", "")

    if "sqlite" in engine:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        db_path = str(db_settings["NAME"])
        conn = sqlite3.connect(db_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        logger.info("LangGraph checkpointer [%s]: SQLite at %s", agent_name, db_path)

    elif "postgres" in engine:
        from langgraph.checkpoint.postgres import PostgresSaver

        try:
            from psycopg_pool import NullConnectionPool as _NullPool
        except ImportError:
            try:
                from psycopg_pool import NullPool as _NullPool  # type: ignore[no-redef]
            except ImportError as exc:
                raise ImportError(
                    "PostgreSQL checkpointer requires psycopg and psycopg-pool. "
                    "Install with: pip install django-langgraph-agent[postgres]"
                ) from exc

        user = db_settings.get("USER", "")
        password = db_settings.get("PASSWORD", "")
        host = db_settings.get("HOST", "localhost")
        port = db_settings.get("PORT", "5432")
        name = db_settings.get("NAME", "")
        conninfo = (
            f"host={host} port={port} dbname={name} "
            f"user={user} password={password} connect_timeout=10"
        )
        pool = _NullPool(conninfo=conninfo, open=True)
        checkpointer = PostgresSaver(pool)
        logger.info("LangGraph checkpointer [%s]: PostgreSQL NullPool", agent_name)

    else:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        logger.warning(
            "LangGraph checkpointer [%s]: falling back to MemorySaver "
            "(unsupported DB engine: %s). State will NOT persist across restarts.",
            agent_name,
            engine,
        )

    _checkpointer_registry[agent_name] = checkpointer
    return checkpointer


def setup_checkpointer(agent_name: str = "default") -> None:
    """
    Creates LangGraph checkpoint tables in the database.
    Call this once at startup via AppConfig.ready() or the management command.
    """
    checkpointer = get_checkpointer(agent_name)
    if hasattr(checkpointer, "setup"):
        checkpointer.setup()
        logger.info("LangGraph checkpoint tables created/verified for agent: %s", agent_name)
