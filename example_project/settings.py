"""
example_project/settings.py

Minimal Django settings for testing django-langgraph-agent with Django Unfold admin theme.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "django-insecure-example-key-do-not-use-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    # Unfold admin theme must be placed before django.contrib.admin
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    
    "django_langgraph_agent",
    "example_project.store",  # Our example store app
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ──────────────────────────────────────────────────────────────────────────────
# django-langgraph-agent Configuration
# ──────────────────────────────────────────────────────────────────────────────
DJANGO_LANGGRAPH_AGENT = {
    "OPENROUTER_API_KEY": "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",
    "DEFAULT_MODEL": "google/gemini-2.5-flash-preview",
    "FALLBACK_MODELS": [
        "google/gemini-2.5-flash",
        "deepseek/deepseek-chat",
    ],
    "SUMMARIZER_MODEL": "deepseek/deepseek-chat",
    "MAX_TOKENS": 800,
    "SUMMARY_THRESHOLD": 6,
    "SITE_URL": "http://localhost:8000",
    "SITE_TITLE": "Example Store Agent",
    "APPROVAL_REQUIRED_TOOLS": ["add_record", "update_record"],
    "PERSIST_MESSAGES": True,
    "MODEL_WHITELIST": {
        "User": {
            "app_label": "auth",
            "display_name": "User",
            "fields": ["id", "username", "email", "first_name", "last_name", "is_active", "is_staff"],
        },
        "Product": {
            "app_label": "store",
            "display_name": "Store Product",
            "fields": ["id", "name", "price", "category", "stock", "is_active"],
        },
        "Order": {
            "app_label": "store",
            "display_name": "Customer Order",
            "exclude_fields": ["payment_reference", "internal_notes", "cost_breakdown"],
        },
    },
    "BLOCKED_FIELD_SUBSTRINGS": [
        "password", "token", "secret", "is_superuser", "is_staff",
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# Django Unfold Configuration
# ──────────────────────────────────────────────────────────────────────────────
UNFOLD = {
    "SITE_TITLE": "Django AI Agent Admin",
    "SITE_HEADER": "Django AI Agent Dashboard",
    "SITE_URL": "/admin/",
    "SHOW_HISTORY": True,
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "🤖 AI Agents & Conversations",
                "separator": True,
                "items": [
                    {
                        "title": "Admin AI Chat Workspace",
                        "icon": "forum",
                        "link": lambda request: "/admin/ai-chat/",
                    },
                    {
                        "title": "Agent Configurations",
                        "icon": "smart_toy",
                        "link": lambda request: "/admin/django_langgraph_agent/agentconfig/",
                    },
                    {
                        "title": "Chat Threads",
                        "icon": "chat",
                        "link": lambda request: "/admin/django_langgraph_agent/chatthread/",
                    },
                    {
                        "title": "Chat Messages Log",
                        "icon": "chat_bubble",
                        "link": lambda request: "/admin/django_langgraph_agent/chatmessage/",
                    },
                ],
            },
            {
                "title": "🛍️ Store Management",
                "separator": True,
                "items": [
                    {
                        "title": "Products",
                        "icon": "inventory_2",
                        "link": lambda request: "/admin/store/product/",
                    },
                    {
                        "title": "Orders",
                        "icon": "shopping_cart",
                        "link": lambda request: "/admin/store/order/",
                    },
                ],
            },
        ],
    },
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"
USE_TZ = True
TIME_ZONE = "UTC"
ROOT_URLCONF = "example_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django_langgraph_agent": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
