"""Resolves media assets from previous pipeline outputs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.core_api_client import CoreApiClient

logger = logging.getLogger(__name__)


class AssetResolver:
    """Extracts media asset references from pipeline outputs."""

    def __init__(self, core_api_client: CoreApiClient) -> None:
        self._client = core_api_client

    async def resolve(
        self,
        job_id: str,
        tenant_id: str,
        previous_outputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Extract asset URIs from previous pipeline node outputs."""
        assets: list[dict[str, Any]] = []

        blog_output = previous_outputs.get("blog_author", {})
        gcs_uri = blog_output.get("gcs_uri", "")
        if gcs_uri:
            assets.append(
                {
                    "uri": gcs_uri,
                    "type": "blog_thumbnail",
                    "alt_text": blog_output.get(
                        "seo_meta", {}
                    ).get("title", "Blog post"),
                }
            )

        return assets
