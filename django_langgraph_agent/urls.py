"""
django_langgraph_agent/urls.py

Built-in URL patterns for django-langgraph-agent.
"""

from django.urls import path

from .api_views import admin_chat_view, approve_view, chat_view, delete_thread_view, list_agents_view

app_name = "django_langgraph_agent"

urlpatterns = [
    path("", list_agents_view, name="list_agents"),
    path("admin-chat/", admin_chat_view, name="admin_chat"),
    path("chat/", chat_view, name="chat"),
    path("chat/approve/", approve_view, name="approve"),
    path("chat/delete/", delete_thread_view, name="delete_thread"),
]

