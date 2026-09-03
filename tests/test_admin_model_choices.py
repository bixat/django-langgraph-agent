"""
tests/test_admin_model_choices.py

Covers issue #11: the allowed_models autocomplete must only offer models the
agent can actually use, and a bad entry must fail at save with a field error
rather than at chat time as a tool-call error string.
"""

import pytest
from django.test import override_settings

from django_langgraph_agent import admin as agent_admin
from django_langgraph_agent.admin import AgentConfigForm


WHITELIST = {
    "Product": {"app_label": "store", "fields": ["id", "name", "price"]},
    "Order": {"app_label": "store"},
}

NO_WHITELIST = {"OPENROUTER_API_KEY": "k", "MODEL_WHITELIST": {}}
WITH_WHITELIST = {"OPENROUTER_API_KEY": "k", "MODEL_WHITELIST": WHITELIST}


def _values(items):
    return {item["value"] for item in items}


# ──────────────────────────────────────────────────────────────────────────────
# Autocomplete source
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_choices_come_from_the_whitelist_when_one_is_configured():
    with override_settings(DJANGO_LANGGRAPH_AGENT=WITH_WHITELIST):
        values = _values(agent_admin._get_all_django_models())
    assert values == {"store.Product", "store.Order"}


@pytest.mark.django_db
def test_bare_whitelist_keys_resolve_to_dotted_labels():
    """MODEL_WHITELIST keys may be bare ("Product"); the widget must still emit
    a usable app_label.ModelName value."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WITH_WHITELIST):
        items = agent_admin._get_all_django_models()
    product = next(i for i in items if i["value"] == "store.Product")
    assert "store" in product["label"]


@pytest.mark.django_db
def test_auth_user_model_is_never_offered_without_a_whitelist():
    with override_settings(DJANGO_LANGGRAPH_AGENT=NO_WHITELIST):
        values = _values(agent_admin._get_all_django_models())
    assert "auth.User" not in values
    assert not any(v.startswith("auth.") for v in values)
    assert "store.Product" in values, "ordinary project models must still be offered"


@pytest.mark.django_db
def test_package_own_models_are_never_offered():
    with override_settings(DJANGO_LANGGRAPH_AGENT=NO_WHITELIST):
        values = _values(agent_admin._get_all_django_models())
    assert not any(v.startswith("django_langgraph_agent.") for v in values)


@pytest.mark.django_db
def test_an_explicitly_whitelisted_user_model_is_still_offered():
    """A project that deliberately whitelists the user model overrides the
    default exclusion — the exclusion is about *suggestions*, not a ban."""
    whitelist = {"User": {"app_label": "auth", "fields": ["id", "username"]}}
    with override_settings(DJANGO_LANGGRAPH_AGENT={"MODEL_WHITELIST": whitelist}):
        values = _values(agent_admin._get_all_django_models())
    assert values == {"auth.User"}


@pytest.mark.django_db
def test_blocked_fields_choices_still_include_auth_field_names():
    """_get_all_model_fields feeds the *blocked_fields* widget, where auth field
    names are exactly what you want to block."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=NO_WHITELIST):
        fields = agent_admin._get_all_model_fields()
    assert "password" in fields
    assert "username" in fields


# ──────────────────────────────────────────────────────────────────────────────
# Save-time validation
# ──────────────────────────────────────────────────────────────────────────────

def _form(allowed_models):
    return AgentConfigForm(
        data={
            "name": "test_agent",
            "display_name": "Test Agent",
            "system_prompt": "You are a test agent.",
            "model_name": "",
            "max_tokens": 800,
            "summary_threshold": 6,
            "allowed_models": allowed_models,
            "blocked_fields": "[]",
            "extra_tools": "[]",
            "extra_approval_tools": "[]",
            "is_active": True,
        }
    )


@pytest.mark.django_db
def test_model_absent_from_whitelist_is_rejected_at_save():
    with override_settings(DJANGO_LANGGRAPH_AGENT=WITH_WHITELIST):
        form = _form('["auth.User"]')
        assert not form.is_valid()
    errors = " ".join(form.errors["allowed_models"])
    assert "Not in MODEL_WHITELIST" in errors
    assert "auth.User" in errors
    assert "Product" in errors, "the error should say what IS allowed"


@pytest.mark.django_db
def test_whitelisted_model_is_accepted():
    with override_settings(DJANGO_LANGGRAPH_AGENT=WITH_WHITELIST):
        form = _form('["store.Product"]')
        assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_bare_name_matches_a_whitelist_key():
    """Matching follows the ORM tools: the part after the last dot, case-insensitively."""
    with override_settings(DJANGO_LANGGRAPH_AGENT=WITH_WHITELIST):
        form = _form('["product"]')
        assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_empty_allowed_models_is_accepted():
    with override_settings(DJANGO_LANGGRAPH_AGENT=WITH_WHITELIST):
        form = _form("[]")
        assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_unresolvable_model_is_rejected_when_no_whitelist_is_configured():
    with override_settings(DJANGO_LANGGRAPH_AGENT=NO_WHITELIST):
        form = _form('["store.NoSuchModel"]')
        assert not form.is_valid()
    assert "Unknown model" in " ".join(form.errors["allowed_models"])


@pytest.mark.django_db
def test_auth_user_model_is_rejected_when_no_whitelist_is_configured():
    with override_settings(DJANGO_LANGGRAPH_AGENT=NO_WHITELIST):
        form = _form('["auth.User"]')
        assert not form.is_valid()
    assert "cannot be exposed" in " ".join(form.errors["allowed_models"])
