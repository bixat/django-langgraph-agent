"""
tests/conftest.py

Shared pytest fixtures for django-langgraph-agent tests.
"""

import django
import pytest
from django.conf import settings


def pytest_configure(config):
    """Configure Django settings for tests."""
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")


@pytest.fixture
def staff_client(client, django_user_model):
    """A test client logged in as a staff user (the default API_PERMISSION)."""
    user = django_user_model.objects.create_user(
        username="staff_api_tester", password="secret", is_staff=True
    )
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def user_client(client, django_user_model):
    """A test client logged in as a non-staff user."""
    user = django_user_model.objects.create_user(
        username="plain_api_tester", password="secret"
    )
    client.force_login(user)
    client.user = user
    return client
