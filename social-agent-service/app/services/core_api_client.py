"""HTTP client for Django backend internal endpoints."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_PERSONA: dict[str, Any] = {
    "name": "Brand",
    "industry": "Technology",
    "brand_voice": "professional",
    "target_audience": "professionals",
    "vision_statement": "",
    "values": [],
    "positioning_statement": "",
    "demographics": "",
    "psychographics": "",
    "pain_points": [],
}


class CoreApiClient:
    """Client for the Django backend's internal service endpoints."""

    def __init__(self, base_url: str, service_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = service_token
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _headers(self, tenant_id: str) -> dict[str, str]:
        return {
            "X-Service-Token": self._token,
            "X-Tenant-ID": tenant_id,
        }

    async def fetch_brand_persona(
        self, tenant_id: str
    ) -> dict[str, Any]:
        """Fetch brand persona from the onboarding companies endpoint."""
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self._base_url}/api/v1/onboarding/companies/",
                headers=self._headers(tenant_id),
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", data) if isinstance(data, dict) else data
            if isinstance(results, list) and results:
                company = results[0]
                return {
                    "name": company.get("name", "Brand"),
                    "industry": company.get("industry", "Technology"),
                    "brand_voice": company.get("brand_voice", "professional"),
                    "target_audience": company.get("target_audience", "professionals"),
                    "vision_statement": company.get("vision_statement", ""),
                    "values": company.get("values", []),
                    "positioning_statement": company.get(
                        "positioning_statement", ""
                    ),
                    "demographics": company.get("demographics", ""),
                    "psychographics": company.get("psychographics", ""),
                    "pain_points": company.get("pain_points", []),
                }
        except Exception as exc:
            logger.warning("Failed to fetch brand persona: %s", exc)

        return dict(_DEFAULT_PERSONA)

    async def fetch_social_profiles(
        self, tenant_id: str, user_id: str | int | None = None
    ) -> list[dict[str, Any]]:
        """Fetch connected social profiles for a tenant."""
        try:
            client = await self._get_client()
            params = {}
            if user_id is not None:
                params["user_id"] = str(user_id)
            resp = await client.get(
                f"{self._base_url}/api/v1/automation/internal/social-profiles/",
                headers=self._headers(tenant_id),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("profiles", [])
        except Exception as exc:
            logger.warning("Failed to fetch social profiles: %s", exc)
            return []

    async def publish_to_platforms(
        self,
        tenant_id: str,
        platforms: list[str],
        content: str,
        title: str,
        user_role: str,
        job_id: str,
        media_urls: list[str] | None = None,
        user_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Delegate publishing to the Django backend."""
        try:
            client = await self._get_client()
            body: dict[str, Any] = {
                "platforms": platforms,
                "content": content,
                "title": title,
                "media_urls": media_urls or [],
                "user_role": user_role,
                "job_id": job_id,
            }
            if user_id is not None:
                body["user_id"] = str(user_id)
            resp = await client.post(
                f"{self._base_url}/api/v1/automation/internal/publish/",
                headers=self._headers(tenant_id),
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("Failed to publish to platforms: %s", exc)
            return {
                "status": "failed",
                "results": {},
                "errors": [str(exc)],
            }

    async def fetch_user_role(
        self, tenant_id: str, user_id: str | int | None = None
    ) -> str:
        """Fetch the user's membership role for a tenant."""
        try:
            client = await self._get_client()
            params = {}
            if user_id is not None:
                params["user_id"] = str(user_id)
            resp = await client.get(
                f"{self._base_url}/api/v1/automation/internal/user-role/",
                headers=self._headers(tenant_id),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("role", "viewer")
        except Exception as exc:
            logger.warning("Failed to fetch user role: %s", exc)
            return "viewer"

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
