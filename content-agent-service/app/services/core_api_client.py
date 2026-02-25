"""
Core API client for fetching brand persona data.

Calls the Django backend's onboarding/companies endpoint to retrieve
brand voice, target audience, and other persona details for a tenant.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Default persona used when core-api is unreachable or no company data exists
_DEFAULT_PERSONA: dict[str, Any] = {
    "name": "Unknown Brand",
    "industry": "General",
    "brand_voice": "professional and informative",
    "target_audience": "business professionals",
    "vision_statement": "",
    "values": [],
    "positioning_statement": "",
    "demographics": "",
    "psychographics": "",
    "pain_points": [],
}


class CoreApiClient:
    """Fetches brand persona from the Django core-api."""

    def __init__(self, base_url: str, service_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize httpx client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def fetch_brand_persona(
        self, tenant_id: str, company_id: str | None = None
    ) -> dict[str, Any]:
        """
        Fetch brand persona data for a tenant.

        GET {base_url}/api/v1/onboarding/companies/
        Headers: X-Tenant-ID, Authorization: Token {service_token}

        Returns the first company's brand data, or a default persona on failure.
        """
        try:
            client = self._get_client()
            headers = {
                "X-Tenant-ID": tenant_id,
                "Authorization": f"Token {self.service_token}",
            }

            url = f"{self.base_url}/api/v1/onboarding/companies/"
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            data = resp.json()

            # Handle paginated or list responses
            results = data if isinstance(data, list) else data.get("results", [])
            if not results:
                logger.info("No companies found for tenant %s, using defaults", tenant_id)
                return dict(_DEFAULT_PERSONA)

            company = results[0]
            return {
                "name": company.get("name", _DEFAULT_PERSONA["name"]),
                "industry": company.get("industry", _DEFAULT_PERSONA["industry"]),
                "brand_voice": company.get(
                    "brand_voice", _DEFAULT_PERSONA["brand_voice"]
                ),
                "target_audience": company.get(
                    "target_audience", _DEFAULT_PERSONA["target_audience"]
                ),
                "vision_statement": company.get("vision_statement", ""),
                "values": company.get("values", []),
                "positioning_statement": company.get("positioning_statement", ""),
                "demographics": company.get("demographics", ""),
                "psychographics": company.get("psychographics", ""),
                "pain_points": company.get("pain_points", []),
            }

        except Exception as exc:
            logger.warning(
                "Failed to fetch brand persona for tenant %s: %s. Using defaults.",
                tenant_id,
                exc,
            )
            return dict(_DEFAULT_PERSONA)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
