"""
tests/test_conf.py

Tests for the settings reader and MODEL_WHITELIST configuration.
"""

import pytest
from django.test import override_settings


@pytest.mark.django_db
def test_defaults_applied():
    """When DJANGO_AI_AGENT settings are cleared, defaults are used."""
    from django_ai_agent.conf import _AgentSettings

    with override_settings(DJANGO_AI_AGENT={}):
        settings_obj = _AgentSettings()
        settings_obj.reload()

        assert settings_obj.MAX_TOKENS == 800
        assert settings_obj.SUMMARY_THRESHOLD == 4
        assert settings_obj.APPROVAL_REQUIRED_TOOLS == []


@pytest.mark.django_db
def test_user_settings_override():
    """User settings override defaults."""
    from django_ai_agent.conf import _AgentSettings

    with override_settings(
        DJANGO_AI_AGENT={
            "OPENROUTER_API_KEY": "test-key",
            "MAX_TOKENS": 1200,
            "APPROVAL_REQUIRED_TOOLS": ["add_record"],
        }
    ):
        s = _AgentSettings()
        s.reload()
        assert s.OPENROUTER_API_KEY == "test-key"
        assert s.MAX_TOKENS == 1200
        assert s.APPROVAL_REQUIRED_TOOLS == ["add_record"]
        # Default still applied for unset keys
        assert s.SUMMARY_THRESHOLD == 4


@pytest.mark.django_db
def test_model_whitelist_config():
    """MODEL_WHITELIST is properly read."""
    from django_ai_agent.conf import _AgentSettings

    with override_settings(
        DJANGO_AI_AGENT={
            "OPENROUTER_API_KEY": "test-key",
            "MODEL_WHITELIST": {
                "Product": {
                    "app_label": "store",
                    "display_name": "Store Product",
                    "fields": ["name", "price"],
                }
            },
        }
    ):
        s = _AgentSettings()
        s.reload()
        whitelist = s.MODEL_WHITELIST
        assert "Product" in whitelist
        assert whitelist["Product"]["app_label"] == "store"
        assert whitelist["Product"]["fields"] == ["name", "price"]
