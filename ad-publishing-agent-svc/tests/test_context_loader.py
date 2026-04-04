"""Tests for AdPubContextLoader — load, enrich_from_backend, _extract_blueprint."""

import pytest
from unittest.mock import patch, AsyncMock

import httpx

from app.services.context_loader import AdPubContextLoader


class TestLoad:
    def setup_method(self):
        self.loader = AdPubContextLoader()

    def test_load_from_previous_outputs(
        self, sample_campaign_blueprint, sample_creative_package
    ):
        previous_outputs = {
            **sample_campaign_blueprint,
            **sample_creative_package,
        }
        context = self.loader.load(
            previous_outputs=previous_outputs,
            input_context={"company": {"name": "Acme"}},
            tenant_context={"tenant_id": "t1"},
            config={"meta_ads_sandbox_mode": True},
        )
        assert context["blueprint"]["campaign_name"] == "Q2 2026 Brand Awareness"
        assert len(context["creative_packages"]) == 1
        assert context["sandbox_mode"] is True
        assert context["_needs_caa_fetch"] is False
        assert context["_needs_cga_fetch"] is False

    def test_load_sets_needs_fetch_flags_when_missing(self):
        context = self.loader.load(
            previous_outputs={},
            input_context={},
            tenant_context={"tenant_id": "t1"},
            config={},
        )
        assert context["_needs_caa_fetch"] is True
        assert context["_needs_cga_fetch"] is True
        assert context["blueprint"]["campaign_name"] == ""

    def test_sandbox_mode_defaults_true(self):
        context = self.loader.load(
            previous_outputs={},
            input_context={},
            tenant_context={},
            config={},
        )
        assert context["sandbox_mode"] is True


class TestEnrichFromBackend:
    def setup_method(self):
        self.loader = AdPubContextLoader()

    @pytest.mark.asyncio
    async def test_enrich_caa_success(self):
        context = {
            "_tenant_id": "t1",
            "_needs_caa_fetch": True,
            "_needs_cga_fetch": False,
            "blueprint": {"campaign_name": ""},
            "creative_packages": [],
            "persona_profiles": [],
        }
        caa_response = httpx.Response(
            200,
            json={
                "blueprint": {
                    "campaign_name": "Fetched Campaign",
                    "objective": "OUTCOME_AWARENESS",
                    "total_budget_usd": 500,
                    "duration_days": 14,
                    "funnel_stages": [{"stage": "TOFU"}],
                    "placements": [],
                    "special_ad_categories": [],
                },
            },
        )

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=caa_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await self.loader.enrich_from_backend(context)

        assert result["blueprint"]["campaign_name"] == "Fetched Campaign"
        assert "_needs_caa_fetch" not in result

    @pytest.mark.asyncio
    async def test_enrich_cga_success(self):
        context = {
            "_tenant_id": "t1",
            "_needs_caa_fetch": False,
            "_needs_cga_fetch": True,
            "blueprint": {"campaign_name": "X"},
            "creative_packages": [],
            "persona_profiles": ["existing"],
        }
        cga_response = httpx.Response(
            200,
            json={
                "creative_packages": [{"ad_units": [{"image_url": "gs://x"}]}],
                "approval_status": "approved",
            },
        )

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=cga_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await self.loader.enrich_from_backend(context)

        assert len(result["creative_packages"]) == 1

    @pytest.mark.asyncio
    async def test_enrich_no_tenant_id_skips(self):
        context = {
            "_tenant_id": "",
            "_needs_caa_fetch": True,
            "_needs_cga_fetch": True,
            "blueprint": {"campaign_name": ""},
            "creative_packages": [],
            "persona_profiles": [],
        }
        result = await self.loader.enrich_from_backend(context)
        # Should return unchanged — no HTTP calls made
        assert result["blueprint"]["campaign_name"] == ""

    @pytest.mark.asyncio
    async def test_enrich_http_error_handled(self):
        context = {
            "_tenant_id": "t1",
            "_needs_caa_fetch": True,
            "_needs_cga_fetch": False,
            "blueprint": {"campaign_name": ""},
            "creative_packages": [],
            "persona_profiles": [],
        }
        error_response = httpx.Response(500, json={"error": "Internal"})

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=error_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await self.loader.enrich_from_backend(context)

        # Should not crash, blueprint stays empty
        assert result["blueprint"]["campaign_name"] == ""

    @pytest.mark.asyncio
    async def test_enrich_network_exception_handled(self):
        context = {
            "_tenant_id": "t1",
            "_needs_caa_fetch": True,
            "_needs_cga_fetch": False,
            "blueprint": {"campaign_name": ""},
            "creative_packages": [],
            "persona_profiles": [],
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await self.loader.enrich_from_backend(context)

        assert result["blueprint"]["campaign_name"] == ""


class TestExtractBlueprint:
    def test_empty_input_returns_defaults(self):
        result = AdPubContextLoader._extract_blueprint({})
        assert result["campaign_name"] == ""
        assert result["objective"] == "OUTCOME_AWARENESS"
        assert result["total_budget_usd"] == 0
        assert result["duration_days"] == 30

    def test_direct_caa_output(self):
        caa = {
            "campaign_name": "Direct",
            "objective": "OUTCOME_TRAFFIC",
            "total_budget_usd": 2000,
            "duration_days": 7,
            "funnel_stages": [{"stage": "MOFU"}],
            "placements": ["FACEBOOK_FEED"],
            "special_ad_categories": [],
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        assert result["campaign_name"] == "Direct"
        assert result["objective"] == "OUTCOME_TRAFFIC"

    def test_nested_blueprint_key(self):
        caa = {
            "blueprint": {
                "campaign_name": "Nested",
                "objective": "OUTCOME_CONVERSIONS",
                "total_budget_usd": 3000,
                "duration_days": 14,
                "funnel_stages": [],
                "placements": [],
                "special_ad_categories": ["HOUSING"],
            }
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        assert result["campaign_name"] == "Nested"
        assert result["special_ad_categories"] == ["HOUSING"]

    def test_preserves_zero_budget(self):
        """Falsy values like 0 should be preserved, not treated as missing."""
        caa = {
            "campaign_name": "Zero Budget Test",
            "total_budget_usd": 0,
            "duration_days": 0,
            "funnel_stages": [],
            "placements": [],
            "special_ad_categories": [],
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        assert result["total_budget_usd"] == 0
        assert result["duration_days"] == 0
        assert result["funnel_stages"] == []

    def test_preserves_empty_list(self):
        """Empty lists should be preserved, not fall through to defaults."""
        caa = {
            "blueprint": {
                "campaign_name": "Test",
                "funnel_stages": [],
                "placements": [],
                "special_ad_categories": [],
            },
            "funnel_stages": [{"stage": "TOFU"}],  # outer fallback
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        # Should use blueprint's empty list, NOT fall through to outer
        assert result["funnel_stages"] == []


class TestExtractCreativePackages:
    def test_empty_input(self):
        assert AdPubContextLoader._extract_creative_packages({}) == []

    def test_from_creative_packages_key(self):
        """Already-mapped format (from cga-context endpoint)."""
        cga = {
            "creative_packages": [
                {"ad_set_name": "TOFU", "ad_units": [{"image_url": "x"}]}
            ]
        }
        result = AdPubContextLoader._extract_creative_packages(cga)
        assert len(result) == 1
        assert result[0]["ad_set_name"] == "TOFU"

    def test_from_ad_set_packages(self):
        """Raw CGA output format (pipeline chaining)."""
        cga = {
            "ad_set_packages": [
                {
                    "ad_set_name": "TOFU - Tech",
                    "persona": "Tech Enthusiast",
                    "funnel_stage": "TOFU",
                    "creative_units": [
                        {"gcs_url": "gs://bucket/img.jpg", "headline": "Test"}
                    ],
                }
            ]
        }
        result = AdPubContextLoader._extract_creative_packages(cga)
        assert len(result) == 1
        assert result[0]["ad_set_name"] == "TOFU - Tech"
        assert result[0]["persona"] == "Tech Enthusiast"
        assert len(result[0]["ad_units"]) == 1

    def test_fallback_to_top_level_ad_units(self):
        """Fallback when neither creative_packages nor ad_set_packages exist."""
        cga = {"ad_units": [{"gcs_url": "gs://bucket/img.jpg", "headline": "Fallback"}]}
        result = AdPubContextLoader._extract_creative_packages(cga)
        assert len(result) == 1
        assert result[0]["ad_set_name"] == "Default"
        assert len(result[0]["ad_units"]) == 1

    def test_no_creative_data(self):
        cga = {"confidence_score": 0.5, "findings": []}
        assert AdPubContextLoader._extract_creative_packages(cga) == []


class TestValidate:
    def setup_method(self):
        self.loader = AdPubContextLoader()

    def test_valid_context(self):
        context = {
            "blueprint": {"campaign_name": "X", "funnel_stages": [{}]},
            "creative_packages": [{"ad_units": [{"image_url": "gs://x"}]}],
            "sandbox_mode": True,
        }
        assert self.loader.validate(context) == []

    def test_sandbox_skips_credential_check(self):
        context = {
            "blueprint": {"campaign_name": "X", "funnel_stages": [{}]},
            "creative_packages": [{"ad_units": [{"image_url": "gs://x"}]}],
            "sandbox_mode": True,
            "meta_credentials": {},
        }
        errors = self.loader.validate(context)
        assert not any("access_token" in e for e in errors)

    def test_production_requires_credentials(self):
        context = {
            "blueprint": {"campaign_name": "X", "funnel_stages": [{}]},
            "creative_packages": [{"ad_units": [{"image_url": "gs://x"}]}],
            "sandbox_mode": False,
            "meta_credentials": {},
        }
        errors = self.loader.validate(context)
        assert any("access_token" in e for e in errors)
        assert any("ad_account_id" in e for e in errors)
