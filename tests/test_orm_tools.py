"""
tests/test_orm_tools.py

Unit tests for Django ORM tools (get_model_schema, query_records, aggregate_model_records, add_record, update_record).
"""

import pytest
from django.test import override_settings

WHITELIST_SETTINGS = {
    "MODEL_WHITELIST": {
        "Order": {
            "app_label": "store",
            "display_name": "Order",
            "exclude_fields": ["internal_notes"],
        },
        "Product": {
            "app_label": "store",
            "display_name": "Product",
            "fields": ["id", "name", "price", "stock"],
        },
    },
    "BLOCKED_FIELD_SUBSTRINGS": ["password", "secret", "token"],
}


@pytest.mark.django_db
def test_get_model_schema_with_allowlist():
    """get_model_schema respects field allowlist."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import get_model_schema

        schema = get_model_schema.invoke({"model_name": "Product"})
        assert "name" in schema
        assert "price" in schema
        assert "stock" in schema
        # cost_price is on Product model but not in 'fields' allowlist
        assert "cost_price" not in schema


@pytest.mark.django_db
def test_get_model_schema_with_exclude():
    """get_model_schema respects exclude_fields."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import get_model_schema

        schema = get_model_schema.invoke({"model_name": "Order"})
        assert "internal_notes" not in schema


@pytest.mark.django_db
def test_model_not_in_whitelist_raises():
    """Querying a model not in whitelist raises a ValueError."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import query_records

        result = query_records.invoke({
            "model_name": "User",  # Not in whitelist
            "filters_json": "{}",
        })
        assert "Error" in result


@pytest.mark.django_db
def test_blocked_field_filter_rejected():
    """Filtering on a globally blocked substring (e.g. password) is rejected."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import query_records

        result = query_records.invoke({
            "model_name": "Order",
            "filters_json": '{"password__icontains": "secret"}',
        })
        assert "Error" in result
        assert "not allowed" in result


@pytest.mark.django_db
def test_excluded_field_filter_rejected():
    """Filtering on an excluded field is rejected."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import query_records

        result = query_records.invoke({
            "model_name": "Order",
            "filters_json": '{"internal_notes": "test"}',
        })
        assert "Error" in result


@pytest.mark.django_db
def test_allowlist_field_filter_rejected():
    """Filtering on a non-allowlisted field is rejected."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import query_records

        # Product allowlist does not include cost_price
        result = query_records.invoke({
            "model_name": "Product",
            "filters_json": '{"cost_price": 5}',
        })
        assert "Error" in result


@pytest.mark.django_db
def test_query_records_returns_data():
    """query_records returns matching serialized records."""
    from example_project.store.models import Product

    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()

        Product.objects.create(name="Widget", price=19.99, stock=10)

        from django_langgraph_agent.tools.django_orm import query_records

        result = query_records.invoke({
            "model_name": "Product",
            "filters_json": '{"name": "Widget"}',
        })
        assert "Widget" in result
        assert "19.99" in result


@pytest.mark.django_db
def test_add_record_creates_product():
    """add_record creates a record and returns serialized result."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import add_record

        result = add_record.invoke({
            "model_name": "Product",
            "data_json": '{"name": "Gadget", "price": "49.99", "stock": 5}',
        })
        assert "✅ Created" in result
        assert "Gadget" in result


@pytest.mark.django_db
def test_add_record_blocked_field_rejected():
    """add_record fails when trying to set a blocked field."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import add_record

        result = add_record.invoke({
            "model_name": "Order",
            "data_json": '{"password": "123"}',
        })
        assert "Error" in result


@pytest.mark.django_db
def test_update_record():
    """update_record successfully updates an existing record."""
    from example_project.store.models import Product

    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()

        product = Product.objects.create(name="Old Name", price=9.99, stock=5)

        from django_langgraph_agent.tools.django_orm import update_record

        result = update_record.invoke({
            "model_name": "Product",
            "record_id": product.pk,
            "data_json": '{"name": "New Name", "stock": 99}',
        })
        assert "✅ Updated" in result

        product.refresh_from_db()
        assert product.name == "New Name"
        assert product.stock == 99


@pytest.mark.django_db
def test_aggregate_model_records():
    """aggregate_model_records computes count, avg, and sum aggregates correctly."""
    from example_project.store.models import Product

    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()

        Product.objects.create(name="P1", price=10.00, stock=5)
        Product.objects.create(name="P2", price=20.00, stock=15)

        from django_langgraph_agent.tools.django_orm import aggregate_model_records

        result = aggregate_model_records.invoke({
            "model_name": "Product",
            "aggregations_json": '[{"type": "count", "field": "id"}, {"type": "avg", "field": "price"}, {"type": "sum", "field": "stock"}]',
        })
        assert "Aggregation Results for Product" in result
        assert '"id_count": 2' in result
        assert '"stock_sum": 20' in result


@pytest.mark.django_db
def test_agent_blocked_fields_enforced():
    """Per-agent blocked_fields passed via runnable config are strictly enforced across schema, query, and write tools."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WHITELIST_SETTINGS):
        from django_langgraph_agent.conf import agent_settings
        agent_settings.reload()
        from django_langgraph_agent.tools.django_orm import (
            get_model_schema,
            query_records,
            add_record,
            aggregate_model_records,
        )

        config = {"configurable": {"blocked_fields": ["status", "stock"]}}

        # get_model_schema should hide 'stock'
        schema = get_model_schema.invoke({"model_name": "Product"}, config=config)
        assert "stock" not in schema

        # Filtering on blocked 'status' should be rejected
        res = query_records.invoke({"model_name": "Product", "filters_json": '{"status": "active"}'}, config=config)
        assert "Error" in res
        assert "not allowed" in res

        # Writing to blocked 'stock' should be rejected
        res_add = add_record.invoke({"model_name": "Product", "data_json": '{"name": "Widget", "price": "10.00", "stock": 10}'}, config=config)
        assert "Error" in res_add
        assert "not allowed" in res_add

        # Aggregating on blocked 'stock' should be rejected
        res_agg = aggregate_model_records.invoke({
            "model_name": "Product",
            "aggregations_json": '[{"type": "sum", "field": "stock"}]'
        }, config=config)
        assert "Error" in res_agg
        assert "not allowed" in res_agg
