"""
tests/test_migrations_and_example.py

Covers:
  * issue #5  — the shipped migrations must match the models, or downstream
                projects get a makemigrations that writes into site-packages
  * issue #1  — the example project's custom tools must register
  * issues #6 / #10 — the chat template's auto-scroll and bubble-overflow fixes
"""

import pytest
from django.apps import apps
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState

APP_LABEL = "django_langgraph_agent"


# ──────────────────────────────────────────────────────────────────────────────
# #5 — migration drift
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_no_missing_migrations_for_the_package():
    """
    Guards the release: a help_text edit on a documented field silently drifts
    the model from its migration, and downstream projects cannot fix it — a
    generated 0003 lands in site-packages and is lost on reinstall.
    """
    loader = MigrationLoader(None, ignore_no_migrations=True)
    autodetector = MigrationAutodetector(
        loader.project_state(),
        ProjectState.from_apps(apps),
        NonInteractiveMigrationQuestioner(specified_apps=set(), dry_run=True),
    )
    changes = autodetector.changes(graph=loader.graph, trim_to_apps={APP_LABEL})

    pending = changes.get(APP_LABEL, [])
    described = [
        f"{op.__class__.__name__}({getattr(op, 'name', '')} on {getattr(op, 'model_name', '')})"
        for migration in pending
        for op in migration.operations
    ]
    assert not pending, f"Missing migration(s) for {APP_LABEL}: {described}"


def test_extra_tools_help_text_matches_the_shipped_migration():
    """The specific drift reported in #5 — the built-in tool list in help_text."""
    from django_langgraph_agent.models import AgentConfig

    help_text = AgentConfig._meta.get_field("extra_tools").help_text
    assert "aggregate_model_records" in help_text


# ──────────────────────────────────────────────────────────────────────────────
# #1 — the example project's custom tools
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "tool_name", ["check_low_stock", "apply_discount", "send_order_confirmation"]
)
def test_example_custom_tools_are_registered(tool_name):
    """StoreConfig.ready() imports store/tools.py, which is what makes the names
    selectable in AgentConfig.extra_tools."""
    from django_langgraph_agent.registry import get_tool

    assert get_tool(tool_name) is not None


def test_example_admin_agent_exposes_the_custom_tools():
    from example_project.store.agents import store_admin_agent

    names = {getattr(t, "name", None) for t in store_admin_agent.tools}
    assert {"check_low_stock", "apply_discount", "send_order_confirmation"} <= names


def test_example_side_effecting_custom_tools_require_approval():
    from example_project.store.agents import store_admin_agent

    assert "apply_discount" in store_admin_agent.approval_tools
    assert "send_order_confirmation" in store_admin_agent.approval_tools


def test_example_customer_agent_gets_no_write_tools():
    """The read-only agent must not pick up the write-side custom tools."""
    from example_project.store.agents import store_agent

    names = {getattr(t, "name", None) for t in store_agent.tools}
    assert "check_low_stock" in names
    assert "apply_discount" not in names
    assert "send_order_confirmation" not in names


@pytest.mark.django_db
def test_check_low_stock_reports_products_at_or_below_threshold():
    from example_project.store.models import Product
    from example_project.store.tools import check_low_stock

    Product.objects.create(name="Nearly Out", price="9.99", stock=2, category="widgets")
    Product.objects.create(name="Plenty", price="9.99", stock=99, category="widgets")

    result = check_low_stock.invoke({"threshold": 5})
    assert "Nearly Out" in result
    assert "Plenty" not in result


@pytest.mark.django_db
def test_apply_discount_rejects_an_out_of_range_percentage():
    from decimal import Decimal

    from example_project.store.models import Product
    from example_project.store.tools import apply_discount

    product = Product.objects.create(name="Gadget", price="100.00", stock=5)
    result = apply_discount.invoke({"product_id": product.pk, "percent": 95})

    assert "Error" in result
    product.refresh_from_db()
    assert product.price == Decimal("100.00"), "price must not change on a rejected call"


@pytest.mark.django_db
def test_apply_discount_updates_the_price():
    from decimal import Decimal

    from example_project.store.models import Product
    from example_project.store.tools import apply_discount

    product = Product.objects.create(name="Gadget", price="100.00", stock=5)
    result = apply_discount.invoke({"product_id": product.pk, "percent": 15})

    product.refresh_from_db()
    assert product.price == Decimal("85.00")
    assert "85.00" in result


# ──────────────────────────────────────────────────────────────────────────────
# #6 / #10 — chat template
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def chat_template_source():
    from django.template.loader import get_template

    return get_template("django_langgraph_agent/chat.html").template.source


def test_transcript_scrolls_through_the_stick_to_bottom_helper(chat_template_source):
    """#6: a bare scrollTop write is a no-op when the panel is not itself
    scrollable, which is what happens inside a host admin layout."""
    src = chat_template_source
    assert "function scrollToBottom(" in src
    assert "scrollIntoView" in src, "needs a fallback for a non-scrollable panel"
    assert "requestAnimationFrame" in src, "must measure after layout"
    # Every pin goes through the helper; the only raw write left is inside it.
    # (The helper's own doc comment names the statement without a semicolon.)
    assert src.count("chatbox.scrollTop = chatbox.scrollHeight;") == 1


def test_streaming_respects_a_user_who_scrolled_up(chat_template_source):
    src = chat_template_source
    assert "stickToBottom" in src
    assert "scroll-behavior: smooth" not in src, (
        "smooth scrolling restarts its animation on every streamed token, "
        "so the view never reaches the bottom"
    )


def test_meta_row_can_shrink_inside_the_bubble(chat_template_source):
    """#10: a flex item defaults to min-width:auto, so a long model slug pushes
    the row past .ai-msg-body's max-width."""
    src = chat_template_source
    meta = src[src.index(".ai-msg-meta {"): src.index(".ai-model-badge {")]
    assert "min-width: 0" in meta
    assert "flex-wrap: wrap" in meta

    badge = src[src.index(".ai-model-badge {"):]
    badge = badge[: badge.index("}")]
    assert "min-width: 0" in badge
    assert "overflow-wrap: anywhere" in badge


@pytest.mark.django_db
def test_rendered_chat_page_carries_the_scroll_and_overflow_fixes(client, django_user_model):
    """End-to-end: the fixes must survive into the page the admin actually serves,
    not just live in the template source."""
    from django_langgraph_agent.models import AgentConfig

    AgentConfig.objects.create(
        name="render_smoke", display_name="Render Smoke", system_prompt="hi", is_active=True
    )
    superuser = django_user_model.objects.create_superuser("render_root", "r@e.com", "pw")
    client.force_login(superuser)

    resp = client.get("/admin/ai-chat/?agent=render_smoke")
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "function scrollToBottom(" in html
    assert "stickToBottom" in html
    assert "overflow-wrap: anywhere" in html
    assert html.count("chatbox.scrollTop = chatbox.scrollHeight;") == 1


@pytest.mark.django_db
def test_agentconfig_admin_form_renders_the_model_autocomplete(client, django_user_model):
    """The choice list is embedded as JSON into help_text — guard the rewrite."""
    superuser = django_user_model.objects.create_superuser("form_root", "f@e.com", "pw")
    client.force_login(superuser)

    resp = client.get("/admin/django_langgraph_agent/agentconfig/add/")
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "initAutocomplete" in html
    assert "store.Product" in html
