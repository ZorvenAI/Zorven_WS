"""
Tests for the internal title-update endpoint used by chat-titling-worker.
"""

import uuid

import pytest
from django.urls import reverse
from rest_framework import status

from ai_services.tests.factories import ChatSessionFactory


@pytest.mark.django_db
@pytest.mark.unit
class TestUpdateSessionTitleInternal:
    """Tests for update_session_title_internal view."""

    def url(self, session_id):
        return reverse(
            "update_session_title_internal",
            kwargs={"session_id": session_id},
        )

    def test_update_title_with_valid_token(self, api_client, public_tenant):
        """PATCH with correct token updates the session title."""
        session = ChatSessionFactory(
            tenant=public_tenant,
            title="Chat 2026-02-25 14:30",
        )

        response = api_client.patch(
            self.url(session.session_id),
            {"title": "NVIDIA Brand Analysis"},
            format="json",
            HTTP_X_WORKER_TOKEN="dev-worker-token",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "updated"

        session.refresh_from_db()
        assert session.title == "NVIDIA Brand Analysis"

    def test_rejects_invalid_token(self, api_client, public_tenant):
        """Wrong token returns 403."""
        session = ChatSessionFactory(
            tenant=public_tenant,
            title="Chat 2026-02-25 14:30",
        )

        response = api_client.patch(
            self.url(session.session_id),
            {"title": "Should Not Update"},
            format="json",
            HTTP_X_WORKER_TOKEN="wrong-token",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        session.refresh_from_db()
        assert session.title == "Chat 2026-02-25 14:30"

    def test_rejects_missing_token(self, api_client, public_tenant):
        """Missing token returns 403."""
        session = ChatSessionFactory(
            tenant=public_tenant,
            title="Chat 2026-02-25 14:30",
        )

        response = api_client.patch(
            self.url(session.session_id),
            {"title": "Should Not Update"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_skips_already_titled_session(self, api_client, public_tenant):
        """Non-'Chat ' title is left unchanged."""
        session = ChatSessionFactory(
            tenant=public_tenant,
            title="My Custom Title",
        )

        response = api_client.patch(
            self.url(session.session_id),
            {"title": "New Title"},
            format="json",
            HTTP_X_WORKER_TOKEN="dev-worker-token",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "already_titled"

        session.refresh_from_db()
        assert session.title == "My Custom Title"

    def test_session_not_found(self, api_client, public_tenant):
        """Non-existent session returns 404."""
        response = api_client.patch(
            self.url("nonexistent-session-id"),
            {"title": "Test Title"},
            format="json",
            HTTP_X_WORKER_TOKEN="dev-worker-token",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_empty_title_returns_400(self, api_client, public_tenant):
        """Empty title string returns 400."""
        session = ChatSessionFactory(
            tenant=public_tenant,
            title="Chat 2026-02-25 14:30",
        )

        response = api_client.patch(
            self.url(session.session_id),
            {"title": ""},
            format="json",
            HTTP_X_WORKER_TOKEN="dev-worker-token",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_title_truncated_to_255(self, api_client, public_tenant):
        """Title longer than 255 chars is truncated."""
        session = ChatSessionFactory(
            tenant=public_tenant,
            title="Chat 2026-02-25 14:30",
        )

        long_title = "A" * 300
        response = api_client.patch(
            self.url(session.session_id),
            {"title": long_title},
            format="json",
            HTTP_X_WORKER_TOKEN="dev-worker-token",
        )

        assert response.status_code == status.HTTP_200_OK

        session.refresh_from_db()
        assert len(session.title) == 255

    def test_invalidates_cache_after_update(
        self, api_client, public_tenant
    ):
        """Cache key is deleted after title update."""
        from unittest.mock import patch

        session = ChatSessionFactory(
            tenant=public_tenant,
            title="Chat 2026-02-25 14:30",
        )

        with patch("ai_services.views.cache") as mock_cache:
            response = api_client.patch(
                self.url(session.session_id),
                {"title": "NVIDIA Analysis"},
                format="json",
                HTTP_X_WORKER_TOKEN="dev-worker-token",
            )

            assert response.status_code == status.HTTP_200_OK
            mock_cache.delete.assert_called_once()
