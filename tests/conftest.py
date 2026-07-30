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
