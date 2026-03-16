"""Tests for workspace WebSocket consumers and middleware."""

import uuid

import pytest
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from workspace.consumers import WorkspaceConsumer
from workspace.middleware import get_user_from_token

User = get_user_model()


def _unique_username(prefix="ws"):
    """Generate a unique username for test users."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.mark.django_db(transaction=True)
class TestGetUserFromToken:
    """Tests for JWT token decoding in WebSocket middleware."""

    def test_valid_token_returns_user(self):
        """A valid JWT token should return the corresponding user."""
        user = User.objects.create_user(
            username=_unique_username("jwt"),
            email=f"jwt_{uuid.uuid4().hex[:6]}@test.com",
            password="testpass",
        )
        # Generate a real JWT token for this user
        from rest_framework_simplejwt.tokens import AccessToken as RealAccessToken

        token = RealAccessToken.for_user(user)

        from asgiref.sync import async_to_sync

        result = async_to_sync(get_user_from_token)(str(token))
        assert result.pk == user.pk

    def test_invalid_token_returns_anonymous(self):
        """An invalid JWT token should return AnonymousUser."""
        from asgiref.sync import async_to_sync

        result = async_to_sync(get_user_from_token)("invalid-garbage-token")
        assert isinstance(result, AnonymousUser)


@pytest.mark.django_db(transaction=True)
class TestWorkspaceConsumer:
    """Tests for the WorkspaceConsumer WebSocket handler."""

    @pytest.mark.asyncio
    async def test_unauthenticated_connection_rejected(self):
        """Anonymous users should be rejected."""
        communicator = WebsocketCommunicator(
            WorkspaceConsumer.as_asgi(),
            "/ws/workspace/1/",
        )
        communicator.scope["url_route"] = {"kwargs": {"tenant_id": "1"}}
        communicator.scope["user"] = AnonymousUser()

        connected, _ = await communicator.connect()
        assert not connected
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_authenticated_connection_accepted(self):
        """Authenticated users should be accepted."""
        user = await User.objects.acreate(
            username=_unique_username("auth"),
            email=f"auth_{uuid.uuid4().hex[:6]}@test.com",
        )
        communicator = WebsocketCommunicator(
            WorkspaceConsumer.as_asgi(),
            "/ws/workspace/1/",
        )
        communicator.scope["url_route"] = {"kwargs": {"tenant_id": "1"}}
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_ping_pong(self):
        """Consumer should respond to ping with pong."""
        user = await User.objects.acreate(
            username=_unique_username("ping"),
            email=f"ping_{uuid.uuid4().hex[:6]}@test.com",
        )
        communicator = WebsocketCommunicator(
            WorkspaceConsumer.as_asgi(),
            "/ws/workspace/1/",
        )
        communicator.scope["url_route"] = {"kwargs": {"tenant_id": "1"}}
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({"type": "ping"})
        response = await communicator.receive_json_from()
        assert response == {"type": "pong"}

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_job_progress_event_forwarded(self):
        """job_progress channel events should be forwarded to client."""
        user = await User.objects.acreate(
            username=_unique_username("prog"),
            email=f"prog_{uuid.uuid4().hex[:6]}@test.com",
        )
        communicator = WebsocketCommunicator(
            WorkspaceConsumer.as_asgi(),
            "/ws/workspace/1/",
        )
        communicator.scope["url_route"] = {"kwargs": {"tenant_id": "1"}}
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        assert connected

        # Send event via channel layer to the group
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "workspace_1",
            {
                "type": "job.progress",
                "data": {
                    "job_id": "test-123",
                    "status": "running",
                    "current_node": "discovery",
                    "progress_percent": 25,
                },
            },
        )

        response = await communicator.receive_json_from()
        assert response["type"] == "job_progress"
        assert response["data"]["job_id"] == "test-123"
        assert response["data"]["status"] == "running"

        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_job_completed_event_forwarded(self):
        """job_completed channel events should be forwarded to client."""
        user = await User.objects.acreate(
            username=_unique_username("comp"),
            email=f"comp_{uuid.uuid4().hex[:6]}@test.com",
        )
        communicator = WebsocketCommunicator(
            WorkspaceConsumer.as_asgi(),
            "/ws/workspace/1/",
        )
        communicator.scope["url_route"] = {"kwargs": {"tenant_id": "1"}}
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        assert connected

        # Send completed event via channel layer
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "workspace_1",
            {
                "type": "job.completed",
                "data": {
                    "job_id": "test-456",
                    "status": "completed",
                    "current_node": None,
                    "progress_percent": 100,
                },
            },
        )

        response = await communicator.receive_json_from()
        assert response["type"] == "job_completed"
        assert response["data"]["status"] == "completed"
        assert response["data"]["progress_percent"] == 100

        await communicator.disconnect()
