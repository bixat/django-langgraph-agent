from django.contrib import admin
from django.urls import include, path

from django_langgraph_agent.api_views import admin_chat_view
from example_project.store.views import approve_view, chat_view

urlpatterns = [
    # Admin AI Chat view (inside admin layout)
    path("admin/ai-chat/", admin.site.admin_view(admin_chat_view), name="admin_ai_chat"),

    # Django Admin Panel (with Unfold theme)
    path("admin/", admin.site.urls),

    # Built-in agent API endpoints (GET /api/agent/, POST /api/agent/chat/, POST /api/agent/chat/approve/)
    path("api/agent/", include("django_langgraph_agent.urls")),

    # Custom test interface view
    path("chat/", chat_view, name="chat"),
    path("chat/approve/", approve_view, name="chat_approve"),
]
