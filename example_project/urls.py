"""
example_project/urls.py

URL configuration for the example project.
All AI agent endpoints come from the package include:
  path("api/agent/", include("django_langgraph_agent.urls"))
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from django_langgraph_agent.api_views import admin_chat_view

urlpatterns = [
    # Admin AI Chat view (inside Django Admin panel layout)
    path("admin/ai-chat/", admin.site.admin_view(admin_chat_view), name="admin_ai_chat"),

    # Django Admin Panel (with Unfold theme)
    path("admin/", admin.site.urls),

    # All built-in agent API endpoints + chat UI
    path("api/agent/", include("django_langgraph_agent.urls")),

    # Root → redirect to admin chat
    path("", RedirectView.as_view(url="/admin/ai-chat/"), name="home"),
]
