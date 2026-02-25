"""Tests for asset resolver."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.logic.asset_resolver import AssetResolver


class TestAssetResolver:
    def _make_resolver(self) -> AssetResolver:
        mock_client = MagicMock()
        return AssetResolver(core_api_client=mock_client)

    async def test_extracts_gcs_uri_from_blog_author(self):
        resolver = self._make_resolver()
        previous_outputs = {
            "blog_author": {
                "gcs_uri": "gs://bucket/tenant/blogs/tesla.md",
                "seo_meta": {"title": "Tesla Blog"},
            }
        }
        assets = await resolver.resolve("job-1", "tenant-1", previous_outputs)
        assert len(assets) == 1
        assert assets[0]["uri"] == "gs://bucket/tenant/blogs/tesla.md"
        assert assets[0]["type"] == "blog_thumbnail"

    async def test_handles_missing_previous_outputs(self):
        resolver = self._make_resolver()
        assets = await resolver.resolve("job-1", "tenant-1", {})
        assert assets == []

    async def test_handles_empty_gcs_uri(self):
        resolver = self._make_resolver()
        previous_outputs = {
            "blog_author": {
                "gcs_uri": "",
                "blog_content": "Some content",
            }
        }
        assets = await resolver.resolve("job-1", "tenant-1", previous_outputs)
        assert assets == []
