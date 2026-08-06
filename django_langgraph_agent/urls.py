"""
django_langgraph_agent/urls.py

Built-in URL patterns for django-langgraph-agent.
"""

from django.urls import path

from .api_views import (
    approve_view,
    chat_page_view,
    chat_view,
    delete_thread_view,
    get_threads_view,
    list_agents_view,
)

app_name = "django_langgraph_agent"

urlpatterns = [
    path("", list_agents_view, name="list_agents"),
    # Admin-protected chat UI (extends admin/base_site.html)
    path("chat/ui/", chat_page_view, name="chat_ui"),
    # SSE endpoints
    path("chat/", chat_view, name="chat"),
    path("chat/approve/", approve_view, name="approve"),
    path("chat/delete/", delete_thread_view, name="delete_thread"),
    # Threads JSON API (agent switcher without page reload)
    path("chat/threads/", get_threads_view, name="get_threads"),
]
