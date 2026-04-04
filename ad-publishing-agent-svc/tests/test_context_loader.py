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
        assert len(context["blueprint"]["funnel_stages"]) == 1
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
        assert result["funnel_stages"] == []

    def test_real_caa_output_format(self):
        """Actual CAA output: blueprint with campaign_objective + ad_sets."""
        caa = {
            "blueprint": {
                "campaign_name": "Q2 Campaign",
                "campaign_objective": "OUTCOME_TRAFFIC",
                "daily_budget": 50.0,
                "ad_sets": [
                    {
                        "name": "MOFU - Browsers",
                        "funnel_stage": "mofu",
                        "placements": ["facebook_feed"],
                        "daily_budget": 50.0,
                    }
                ],
            },
            "funnel_map": {
                "stages": [
                    {"stage": "mofu", "meta_objective": "OUTCOME_TRAFFIC"}
                ]
            },
            "special_ad_category": "",
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        assert result["campaign_name"] == "Q2 Campaign"
        assert result["objective"] == "OUTCOME_TRAFFIC"
        assert result["daily_budget"] == 50.0
        assert len(result["funnel_stages"]) == 1
        assert result["funnel_stages"][0]["funnel_stage"] == "mofu"
        assert result["placements"] == ["facebook_feed"]

    def test_caa_context_endpoint_response(self):
        """Response from /api/v1/analytics/caa-context/."""
        caa = {
            "blueprint": {
                "campaign_name": "From Endpoint",
                "campaign_objective": "OUTCOME_CONVERSIONS",
                "daily_budget": 100.0,
                "ad_sets": [
                    {
                        "name": "BOFU - Buyers",
                        "funnel_stage": "bofu",
                        "placements": ["instagram_feed"],
                    }
                ],
            },
            "funnel_map": {
                "stages": [{"stage": "bofu", "budget_pct": 100}]
            },
            "special_ad_category": "HOUSING",
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        assert result["campaign_name"] == "From Endpoint"
        assert result["special_ad_categories"] == ["HOUSING"]
        assert len(result["funnel_stages"]) == 1

    def test_funnel_map_fallback(self):
        """When blueprint has no ad_sets, fall back to funnel_map.stages."""
        caa = {
            "blueprint": {
                "campaign_name": "Map Only",
                "campaign_objective": "OUTCOME_AWARENESS",
                "daily_budget": 30.0,
            },
            "funnel_map": {
                "stages": [
                    {"stage": "tofu", "meta_objective": "OUTCOME_AWARENESS"},
                    {"stage": "mofu", "meta_objective": "OUTCOME_TRAFFIC"},
                ]
            },
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        assert len(result["funnel_stages"]) == 2

    def test_preserves_zero_budget(self):
        """Falsy values like 0 should be preserved, not treated as missing."""
        caa = {
            "blueprint": {
                "campaign_name": "Zero Budget Test",
                "daily_budget": 0,
                "ad_sets": [],
            },
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        assert result["daily_budget"] == 0
        assert result["funnel_stages"] == []

    def test_legacy_format_backward_compatible(self):
        """Legacy format with funnel_stages and objective still works."""
        caa = {
            "campaign_name": "Legacy",
            "objective": "OUTCOME_TRAFFIC",
            "total_budget_usd": 2000,
            "duration_days": 7,
            "funnel_stages": [{"stage": "MOFU"}],
            "placements": ["FACEBOOK_FEED"],
            "special_ad_categories": ["CREDIT"],
        }
        result = AdPubContextLoader._extract_blueprint(caa)
        assert result["campaign_name"] == "Legacy"
        assert result["objective"] == "OUTCOME_TRAFFIC"
        assert len(result["funnel_stages"]) == 1
        assert result["special_ad_categories"] == ["CREDIT"]


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
            "blueprint": {
                "campaign_name": "X",
                "funnel_stages": [{"funnel_stage": "tofu"}],
            },
            "creative_packages": [{"ad_units": [{"image_url": "gs://x"}]}],
            "sandbox_mode": True,
        }
        assert self.loader.validate(context) == []

    def test_sandbox_skips_credential_check(self):
        context = {
            "blueprint": {
                "campaign_name": "X",
                "funnel_stages": [{"funnel_stage": "tofu"}],
            },
            "creative_packages": [{"ad_units": [{"image_url": "gs://x"}]}],
            "sandbox_mode": True,
            "meta_credentials": {},
        }
        errors = self.loader.validate(context)
        assert not any("access_token" in e for e in errors)

    def test_production_requires_credentials(self):
        context = {
            "blueprint": {
                "campaign_name": "X",
                "funnel_stages": [{"funnel_stage": "tofu"}],
            },
            "creative_packages": [{"ad_units": [{"image_url": "gs://x"}]}],
            "sandbox_mode": False,
            "meta_credentials": {},
        }
        errors = self.loader.validate(context)
        assert any("access_token" in e for e in errors)
        assert any("ad_account_id" in e for e in errors)

    def test_failure_diagnostics_included_in_errors(self):
        """Backend fetch failures are surfaced in validation errors."""
        context = {
            "blueprint": {"campaign_name": "", "funnel_stages": []},
            "creative_packages": [],
            "sandbox_mode": True,
            "_backend_diagnostics": [
                "CAA fetch failed: HTTP 404 from http://x/caa-context/"
            ],
        }
        errors = self.loader.validate(context)
        assert any("Backend enrichment errors" in e for e in errors)
        assert any("HTTP 404" in e for e in errors)

    def test_success_diagnostics_not_in_errors(self):
        """Successful fetch diagnostics are stored as info, not errors."""
        context = {
            "blueprint": {
                "campaign_name": "X",
                "funnel_stages": [{"funnel_stage": "tofu"}],
            },
            "creative_packages": [{"ad_units": [{"gcs_url": "gs://x"}]}],
            "sandbox_mode": True,
            "_backend_diagnostics": [
                "CAA fetch OK: campaign=X",
                "CGA fetch OK: 1 packages",
            ],
        }
        errors = self.loader.validate(context)
        assert errors == []
        assert context["_diagnostics_info"] == [
            "CAA fetch OK: campaign=X",
            "CGA fetch OK: 1 packages",
        ]
