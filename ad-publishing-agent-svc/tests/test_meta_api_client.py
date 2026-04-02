"""Tests for the Meta Marketing API client wrapper."""

import pytest

from app.services.meta_api_client import MetaApiClient


class TestMetaApiClientStubs:
    """Test stub mode (no facebook-business SDK)."""

    def setup_method(self):
        self.client = MetaApiClient(sandbox_mode=True)
        # Don't call initialize — keeps _api as None (stub mode)

    async def test_validate_account_stub(self):
        result = await self.client.validate_account("12345")
        assert result["token_valid"] is True
        assert result["all_passed"] is True
        assert result["account_status"] == 1

    async def test_create_campaign_stub(self):
        campaign_id = await self.client.create_campaign(
            ad_account_id="12345",
            name="Test Campaign",
            objective="OUTCOME_AWARENESS",
        )
        assert campaign_id.startswith("stub_campaign_")

    async def test_create_ad_set_stub(self):
        ad_set_id = await self.client.create_ad_set(
            ad_account_id="12345",
            campaign_id="campaign_123",
            name="TOFU - Tech",
            targeting={"geo_locations": {"countries": ["US"]}},
            optimization_goal="REACH",
            billing_event="IMPRESSIONS",
            daily_budget_cents=5000,
        )
        assert ad_set_id.startswith("stub_adset_")

    async def test_upload_image_stub(self):
        result = await self.client.upload_image(
            ad_account_id="12345",
            image_bytes=b"fake_image",
            name="test.jpg",
        )
        assert "hash" in result
        assert "url" in result

    async def test_create_ad_creative_stub(self):
        creative_id = await self.client.create_ad_creative(
            ad_account_id="12345",
            name="Creative A",
            image_hash="abc123",
            headline="Test Headline",
            body="Test body text",
            cta_type="LEARN_MORE",
            link_url="https://example.com",
        )
        assert creative_id.startswith("stub_creative_")

    async def test_create_ad_stub(self):
        ad_id = await self.client.create_ad(
            ad_account_id="12345",
            ad_set_id="adset_456",
            creative_id="creative_789",
            name="Ad Variant A",
        )
        assert ad_id.startswith("stub_ad_")

    async def test_update_campaign_status_stub(self):
        result = await self.client.update_campaign_status(
            "campaign_123", "ACTIVE"
        )
        assert result is True

    async def test_get_ad_preview_stub(self):
        preview = await self.client.get_ad_preview("creative_789")
        assert "creative_789" in preview

    async def test_pause_entities_stub(self):
        entities = [
            {"type": "campaign", "id": "c1"},
            {"type": "ad_set", "id": "as1"},
        ]
        results = await self.client.pause_entities(entities)
        assert len(results) == 2
        assert all(r["paused"] for r in results)

    async def test_pause_entities_reverse_order(self):
        """Entities should be paused in reverse order for safe rollback."""
        entities = [
            {"type": "campaign", "id": "first"},
            {"type": "ad_set", "id": "second"},
        ]
        results = await self.client.pause_entities(entities)
        # Reversed: second first, then first
        assert results[0]["id"] == "second"
        assert results[1]["id"] == "first"


class TestMetaApiClientSandboxMode:
    """Test sandbox mode flag."""

    def test_default_sandbox_true(self):
        client = MetaApiClient()
        assert client.sandbox_mode is True

    def test_explicit_production(self):
        client = MetaApiClient(sandbox_mode=False)
        assert client.sandbox_mode is False
