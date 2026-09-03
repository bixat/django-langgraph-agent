"""
tests/test_checkpointer.py

Regression coverage for issue #8: the PostgreSQL pool must be opened in
autocommit mode, or PostgresSaver.setup() fails with
"CREATE INDEX CONCURRENTLY cannot run inside a transaction block".

psycopg / langgraph-checkpoint-postgres are optional extras, so the modules are
stubbed here rather than requiring a live PostgreSQL.
"""

import sys
import types

import pytest
from django.conf import settings

import django_langgraph_agent.checkpointer as checkpointer_module


class _FakePool:
    instances = []

    def __init__(self, conninfo=None, open=False, kwargs=None, **extra):
        self.conninfo = conninfo
        self.opened = open
        self.kwargs = kwargs or {}
        self.closed = False
        _FakePool.instances.append(self)

    def close(self):
        self.closed = True


class _FakePostgresSaver:
    def __init__(self, pool):
        self.pool = pool

    def setup(self):
        if not self.pool.kwargs.get("autocommit"):
            raise RuntimeError("CREATE INDEX CONCURRENTLY cannot run inside a transaction block")


POSTGRES_DB = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "agentdb",
        "USER": "agent",
        "PASSWORD": "secret",
        "HOST": "localhost",
        "PORT": "5432",
    }
}


@pytest.fixture
def fake_postgres(monkeypatch):
    """Stubs psycopg_pool, langgraph.checkpoint.postgres, and a PostgreSQL DATABASES."""
    _FakePool.instances = []

    pool_mod = types.ModuleType("psycopg_pool")
    pool_mod.NullConnectionPool = _FakePool
    monkeypatch.setitem(sys.modules, "psycopg_pool", pool_mod)

    pg_mod = types.ModuleType("langgraph.checkpoint.postgres")
    pg_mod.PostgresSaver = _FakePostgresSaver
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres", pg_mod)

    monkeypatch.setattr(settings, "DATABASES", POSTGRES_DB, raising=False)

    checkpointer_module._checkpointer_registry.clear()
    checkpointer_module._open_pools.clear()
    yield
    checkpointer_module._checkpointer_registry.clear()
    checkpointer_module._open_pools.clear()


def test_postgres_pool_opens_in_autocommit(fake_postgres):
    checkpointer_module.get_checkpointer("pg-agent")

    pool = _FakePool.instances[-1]
    assert pool.kwargs.get("autocommit") is True


def test_setup_checkpointer_succeeds_on_postgres(fake_postgres):
    """setup() raises unless the pool is in autocommit — this is issue #8."""
    checkpointer_module.setup_checkpointer("pg-agent")


def test_pools_are_closed_on_shutdown(fake_postgres):
    """Unclosed pools leave psycopg worker threads warning at exit."""
    checkpointer_module.get_checkpointer("pg-agent")

    pool = _FakePool.instances[-1]
    assert pool.closed is False

    checkpointer_module.close_checkpointers()
    assert pool.closed is True
    assert checkpointer_module._checkpointer_registry == {}


def test_sqlite_backend_is_unaffected():
    checkpointer_module._checkpointer_registry.pop("sqlite-agent", None)
    saver = checkpointer_module.get_checkpointer("sqlite-agent")
    assert type(saver).__name__ == "SqliteSaver"
    checkpointer_module._checkpointer_registry.pop("sqlite-agent", None)
