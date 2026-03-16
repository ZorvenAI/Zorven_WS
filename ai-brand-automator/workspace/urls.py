from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"workflows", views.WorkflowViewSet, basename="workflow")

urlpatterns = [
    path("agents/", views.agent_catalog, name="workspace-agents"),
    path("link-from-chat/", views.link_from_chat, name="workspace-link-from-chat"),
    path("", include(router.urls)),
]
