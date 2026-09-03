"""
tests/test_scoping_and_serialization.py

Regression coverage for:
  - issue #3: QUERYSET_SCOPE / WRITE_DEFAULTS row-level scoping for the ORM tools
  - issue #7: _serialize_qs must not fail on unrecognised field types
  - issue #4: summarization must keep the newest HumanMessage
"""

import json
import uuid
from decimal import Decimal

import pytest
from django.test import override_settings

from example_project.store.models import Product

SCOPE_SETTINGS = {
    "MODEL_WHITELIST": {
        "Product": {
            "app_label": "store",
            "display_name": "Product",
            "fields": ["id", "name", "price", "stock", "category"],
        },
    },
    "BLOCKED_FIELD_SUBSTRINGS": ["password", "secret", "token"],
}


def _only_widgets(model, config):
    """Test scope hook: restrict every model to the 'widgets' category."""
    return {"category": "widgets"}


def _force_widgets(model, config):
    """Test write hook: force category, whatever the model supplied."""
    return {"category": "widgets"}


@pytest.fixture
def products(db):
    Product.objects.create(name="In scope", price=Decimal("10.00"), stock=1, category="widgets")
    Product.objects.create(name="Out of scope", price=Decimal("20.00"), stock=2, category="gadgets")


def _settings(**extra):
    return {**SCOPE_SETTINGS, **extra}


# ── issue #3: row-level scoping ──────────────────────────────────────────────

@pytest.mark.django_db
def test_query_records_is_unscoped_without_the_hook(products):
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings()):
        from django_langgraph_agent.tools.django_orm import query_records

        result = json.loads(query_records.invoke({"model_name": "Product"}))
        assert result["total"] == 2


@pytest.mark.django_db
def test_queryset_scope_narrows_reads(products):
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(QUERYSET_SCOPE=_only_widgets)):
        from django_langgraph_agent.tools.django_orm import query_records

        result = json.loads(query_records.invoke({"model_name": "Product"}))
        assert result["total"] == 1
        assert [r["name"] for r in result["results"]] == ["In scope"]


@pytest.mark.django_db
def test_queryset_scope_narrows_aggregates(products):
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(QUERYSET_SCOPE=_only_widgets)):
        from django_langgraph_agent.tools.django_orm import aggregate_model_records

        result = aggregate_model_records.invoke({"model_name": "Product"})
        assert "1" in result

        detailed = aggregate_model_records.invoke({
            "model_name": "Product",
            "aggregations_json": json.dumps([{"type": "sum", "field": "stock"}]),
        })
        assert '"stock_sum": 1' in detailed


@pytest.mark.django_db
def test_queryset_scope_accepts_a_queryset(products):
    def scope(model, config):
        return model.objects.filter(category="gadgets")

    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(QUERYSET_SCOPE=scope)):
        from django_langgraph_agent.tools.django_orm import query_records

        result = json.loads(query_records.invoke({"model_name": "Product"}))
        assert [r["name"] for r in result["results"]] == ["Out of scope"]


@pytest.mark.django_db
def test_queryset_scope_blocks_out_of_scope_update(products):
    out_of_scope = Product.objects.get(name="Out of scope")

    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(QUERYSET_SCOPE=_only_widgets)):
        from django_langgraph_agent.tools.django_orm import update_record

        result = update_record.invoke({
            "model_name": "Product",
            "record_id": out_of_scope.pk,
            "data_json": json.dumps({"name": "Hijacked"}),
        })

    assert result.startswith("Error:")
    out_of_scope.refresh_from_db()
    assert out_of_scope.name == "Out of scope"


@pytest.mark.django_db
def test_queryset_scope_allows_in_scope_update(products):
    in_scope = Product.objects.get(name="In scope")

    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(QUERYSET_SCOPE=_only_widgets)):
        from django_langgraph_agent.tools.django_orm import update_record

        result = update_record.invoke({
            "model_name": "Product",
            "record_id": in_scope.pk,
            "data_json": json.dumps({"name": "Renamed"}),
        })

    assert result.startswith("✅")
    in_scope.refresh_from_db()
    assert in_scope.name == "Renamed"


@pytest.mark.django_db
def test_write_defaults_override_model_supplied_values(db):
    """The hook is authoritative — a model-chosen value cannot win."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(WRITE_DEFAULTS=_force_widgets)):
        from django_langgraph_agent.tools.django_orm import add_record

        result = add_record.invoke({
            "model_name": "Product",
            "data_json": json.dumps({"name": "New", "price": "5.00", "category": "gadgets"}),
        })

    assert result.startswith("✅")
    assert Product.objects.get(name="New").category == "widgets"


@pytest.mark.django_db
def test_write_defaults_bypass_the_field_allowlist(db):
    """
    Hook values are applied *after* key validation, so a hook can set keys the
    `fields` allowlist rejects — which is what a concrete `<fk>_id` tenant key
    needs (the allowlist lists `organization`, the write needs
    `organization_id`).
    """
    payload = json.dumps({"name": "Scoped", "price": "1.00"})

    # is_active is not in the allowlist, so the model may not set it...
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings()):
        from django_langgraph_agent.tools.django_orm import add_record

        rejected = add_record.invoke({
            "model_name": "Product",
            "data_json": json.dumps({"name": "Nope", "price": "1.00", "is_active": False}),
        })
        assert rejected.startswith("Error:")

    # ...but the hook can.
    with override_settings(
        DJANGO_LANGGRAPH_AGENT=_settings(WRITE_DEFAULTS=lambda model, config: {"is_active": False})
    ):
        result = add_record.invoke({"model_name": "Product", "data_json": payload})

    assert result.startswith("✅")
    assert Product.objects.get(name="Scoped").is_active is False


@pytest.mark.django_db
def test_scope_hook_accepts_a_dotted_path(products):
    dotted = "tests.test_scoping_and_serialization._only_widgets"
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(QUERYSET_SCOPE=dotted)):
        from django_langgraph_agent.tools.django_orm import query_records

        result = json.loads(query_records.invoke({"model_name": "Product"}))
        assert result["total"] == 1


@pytest.mark.django_db
def test_scope_hook_receives_the_runnable_config(products):
    seen = {}

    def scope(model, config):
        seen["config"] = config
        return None

    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings(QUERYSET_SCOPE=scope)):
        from django_langgraph_agent.tools.django_orm import query_records

        query_records.invoke(
            {"model_name": "Product"},
            config={"configurable": {"user_id": 7}},
        )

    assert seen["config"]["configurable"]["user_id"] == 7


# ── issue #7: serialization of unrecognised field types ──────────────────────

class _PhoneNumber:
    """Stands in for django-phonenumber-field's PhoneNumber: no isoformat, no pk."""

    def __init__(self, raw):
        self.raw = raw

    def __str__(self):
        return self.raw


@pytest.mark.parametrize("value,expected", [
    (_PhoneNumber("+966500111222"), "+966500111222"),
    (uuid.UUID("12345678-1234-5678-1234-567812345678"), "12345678-1234-5678-1234-567812345678"),
    (Decimal("10.50"), "10.50"),
    ("plain", "plain"),
    (7, 7),
    (True, True),
    (None, None),
])
def test_to_jsonable_coerces_unknown_types(value, expected):
    from django_langgraph_agent.tools.django_orm import _to_jsonable

    assert _to_jsonable(value) == expected


def test_serialize_qs_output_is_json_dumpable():
    """A single unrecognised field type used to break every read tool."""
    from django_langgraph_agent.tools.django_orm import _serialize_qs

    class Row:
        phone = _PhoneNumber("+966500111222")
        uid = uuid.uuid4()
        name = "Contact"

    rows = _serialize_qs([Row()], ["name", "phone", "uid"])
    json.dumps(rows)  # must not raise
    assert rows[0]["phone"] == "+966500111222"


@pytest.mark.django_db
def test_query_records_serializes_decimals(products):
    with override_settings(DJANGO_LANGGRAPH_AGENT=_settings()):
        from django_langgraph_agent.tools.django_orm import query_records

        result = json.loads(query_records.invoke({"model_name": "Product"}))
        assert all(isinstance(r["price"], str) for r in result["results"])


# ── issue #4: summarization keeps the question being answered ────────────────

def test_summarize_keeps_the_newest_human_message():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from django_langgraph_agent.graph import _summarize_node

    question = HumanMessage(content="how many contacts do we have?", id="h2")
    messages = [
        HumanMessage(content="hello", id="h1"),
        AIMessage(content="hi", id="a1"),
        question,
        AIMessage(content="", id="a2", tool_calls=[
            {"id": "tc1", "name": "aggregate_model_records", "args": {}}
        ]),
        ToolMessage(content="28", tool_call_id="tc1", id="t1"),
    ]

    class _StubLLM:
        def invoke(self, msgs):
            return AIMessage(content="Summary of the conversation.")

    result = _summarize_node({"messages": messages, "summary": ""}, None, _StubLLM())

    removed = {m.id for m in result["messages"]}
    assert question.id not in removed, "the question being answered must survive"
    assert removed == {"h1", "a1"}


def test_summarize_still_compacts_older_history():
    from langchain_core.messages import AIMessage, HumanMessage

    from django_langgraph_agent.graph import _summarize_node

    messages = [
        HumanMessage(content="first", id="h1"),
        AIMessage(content="one", id="a1"),
        HumanMessage(content="second", id="h2"),
        AIMessage(content="two", id="a2"),
    ]

    class _StubLLM:
        def invoke(self, msgs):
            return AIMessage(content="Summary.")

    result = _summarize_node({"messages": messages, "summary": ""}, None, _StubLLM())
    assert {m.id for m in result["messages"]} == {"h1", "a1"}
    assert result["summary"] == "Summary."
