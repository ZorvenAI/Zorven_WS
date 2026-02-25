"""Tests for the CoreApiClient."""

from __future__ import annotations

import pytest

from app.services.core_api_client import CoreApiClient


class TestFetchSocialProfiles:
    async def test_fetch_social_profiles(self, httpx_mock):
        httpx_mock.add_response(
            url="http://test:8001/api/v1/automation/internal/social-profiles/",
            json={
                "profiles": [
                    {
                        "id": 1,
                        "platform": "linkedin",
                        "status": "connected",
                        "profile_name": "John Doe",
                        "is_token_valid": True,
                    }
                ]
            },
        )
        client = CoreApiClient("http://test:8001", "test-token")
        profiles = await client.fetch_social_profiles("tenant-1")
        assert len(profiles) == 1
        assert profiles[0]["platform"] == "linkedin"
        await client.close()

    async def test_handles_api_failure_gracefully(self, httpx_mock):
        httpx_mock.add_response(
            url="http://test:8001/api/v1/automation/internal/social-profiles/",
            status_code=500,
        )
        client = CoreApiClient("http://test:8001", "test-token")
        profiles = await client.fetch_social_profiles("tenant-1")
        assert profiles == []
        await client.close()


class TestPublishToPlatforms:
    async def test_publish_to_platforms(self, httpx_mock):
        httpx_mock.add_response(
            url="http://test:8001/api/v1/automation/internal/publish/",
            json={
                "status": "published",
                "results": {"linkedin": {"post_id": "urn:li:share:123"}},
                "errors": [],
            },
        )
        client = CoreApiClient("http://test:8001", "test-token")
        result = await client.publish_to_platforms(
            tenant_id="tenant-1",
            platforms=["linkedin"],
            content="Test post",
            title="Test",
            user_role="admin",
            job_id="job-1",
        )
        assert result["status"] == "published"
        await client.close()


class TestFetchUserRole:
    async def test_fetch_user_role(self, httpx_mock):
        httpx_mock.add_response(
            url="http://test:8001/api/v1/automation/internal/user-role/?user_id=42",
            json={"role": "admin", "user_id": 42},
        )
        client = CoreApiClient("http://test:8001", "test-token")
        role = await client.fetch_user_role("tenant-1", user_id=42)
        assert role == "admin"
        await client.close()

    async def test_fetch_user_role_default_on_error(self, httpx_mock):
        httpx_mock.add_response(
            url="http://test:8001/api/v1/automation/internal/user-role/",
            status_code=404,
        )
        client = CoreApiClient("http://test:8001", "test-token")
        role = await client.fetch_user_role("tenant-1")
        assert role == "viewer"
        await client.close()


class TestFetchBrandPersona:
    async def test_fetch_brand_persona(self, httpx_mock):
        httpx_mock.add_response(
            url="http://test:8001/api/v1/onboarding/companies/",
            json={
                "results": [
                    {
                        "name": "Acme Corp",
                        "industry": "Tech",
                        "brand_voice": "professional",
                        "target_audience": "developers",
                    }
                ]
            },
        )
        client = CoreApiClient("http://test:8001", "test-token")
        persona = await client.fetch_brand_persona("tenant-1")
        assert persona["name"] == "Acme Corp"
        assert persona["industry"] == "Tech"
        await client.close()

    async def test_returns_default_on_failure(self, httpx_mock):
        httpx_mock.add_response(
            url="http://test:8001/api/v1/onboarding/companies/",
            status_code=500,
        )
        client = CoreApiClient("http://test:8001", "test-token")
        persona = await client.fetch_brand_persona("tenant-1")
        assert persona["name"] == "Brand"
        assert persona["brand_voice"] == "professional"
        await client.close()
