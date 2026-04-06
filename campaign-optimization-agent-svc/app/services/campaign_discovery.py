"""SKL-COA-01: Campaign discovery from Django backend.

Discovers active campaigns and loads tenant configuration.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass
class ActiveCampaign:
    """Represents an active campaign ready for optimization."""

    campaign_id: str = ""
    tenant_id: str = ""
    meta_campaign_id: str = ""
    meta_ad_account_id: str = ""
    meta_access_token: str = ""
    campaign_name: str = ""
    status: str = "active"
    objective: str = ""
    daily_budget: float = 0.0
    total_spend_usd: float = 0.0
    total_impressions: int = 0
    created_at: str = ""
    last_optimized_at: str = ""
    optimization_count: int = 0
    sandbox_mode: bool = True
    active_ad_set_count: int = 0
    ad_sets: list[dict[str, Any]] = field(default_factory=list)
    ads: list[dict[str, Any]] = field(default_factory=list)
    targets: dict[str, Any] = field(default_factory=dict)
    daily_action_count: int = 0


class CampaignDiscovery:
    """Discovers active campaigns from Django backend."""

    def __init__(self, redis_manager=None):
        self._base_url = settings.backend_url
        self._headers = {
            "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
            "Content-Type": "application/json",
        }
        self._redis = redis_manager

    async def discover_active_campaigns(
        self,
        age_min_days: int | None = None,
        age_max_days: int | None = None,
    ) -> list[ActiveCampaign]:
        """Fetch active campaigns from Django and filter by age range.

        Args:
            age_min_days: Minimum campaign age in days (inclusive).
            age_max_days: Maximum campaign age in days (exclusive).

        Returns:
            List of ActiveCampaign objects matching the age range.
        """
        url = (
            f"{self._base_url}/api/v1/optimization"
            f"/campaigns/?status=active"
        )
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
                campaigns_data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Campaign discovery failed (HTTP %d): %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return []
        except Exception as exc:
            logger.error("Campaign discovery failed: %s", exc)
            return []

        # Parse and filter by age range
        if isinstance(campaigns_data, dict):
            campaigns_data = campaigns_data.get("results", [])

        campaigns = []
        now = datetime.now(timezone.utc)

        for data in campaigns_data:
            campaign = ActiveCampaign(
                campaign_id=data.get("campaign_id", ""),
                tenant_id=data.get("tenant_id", ""),
                meta_campaign_id=data.get("meta_campaign_id", ""),
                meta_ad_account_id=data.get("meta_ad_account_id", ""),
                meta_access_token=data.get("meta_access_token", ""),
                campaign_name=data.get("campaign_name", ""),
                status=data.get("status", "active"),
                objective=data.get("objective", ""),
                daily_budget=float(data.get("daily_budget", 0)),
                total_spend_usd=float(data.get("total_spend_usd", 0)),
                total_impressions=int(data.get("total_impressions", 0)),
                created_at=data.get("created_at", ""),
                last_optimized_at=data.get("last_optimized_at", ""),
                optimization_count=int(
                    data.get("optimization_count", 0)
                ),
                sandbox_mode=data.get("sandbox_mode", True),
                active_ad_set_count=int(
                    data.get("active_ad_set_count", 0)
                ),
                ad_sets=data.get("ad_sets", []),
                ads=data.get("ads", []),
                targets=data.get("targets", {}),
            )

            # Filter by age range
            if campaign.created_at:
                try:
                    created = datetime.fromisoformat(campaign.created_at)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age_days = (now - created).days
                    if age_min_days is not None and age_days < age_min_days:
                        continue
                    if age_max_days is not None and age_days >= age_max_days:
                        continue
                except (ValueError, TypeError):
                    logger.warning(
                        "Invalid created_at for campaign %s",
                        campaign.campaign_id,
                    )
                    continue

            # Load daily action count from Redis
            if self._redis and campaign.tenant_id:
                try:
                    count = await self._redis.get_action_counter(
                        campaign.tenant_id
                    )
                    campaign.daily_action_count = count
                except Exception:
                    pass

            campaigns.append(campaign)

        logger.info(
            "Discovered %d active campaigns (age_min=%s, age_max=%s)",
            len(campaigns),
            age_min_days,
            age_max_days,
        )
        return campaigns

    async def load_tenant_config(
        self, tenant_id: str
    ) -> dict[str, Any]:
        """Load tenant optimization configuration.

        First checks Redis cache, then falls back to Django API.
        """
        # Check Redis cache
        if self._redis:
            try:
                config = await self._redis.get_tenant_config(tenant_id)
                if config:
                    return config
            except Exception:
                pass

        # Fetch from Django
        url = (
            f"{self._base_url}/api/v1/optimization"
            f"/tenants/{tenant_id}/config/"
        )
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
                config = response.json()

            # Cache in Redis
            if self._redis:
                try:
                    await self._redis.set_tenant_config(tenant_id, config)
                except Exception:
                    pass

            return config
        except Exception as exc:
            logger.warning(
                "Failed to load tenant config for %s: %s", tenant_id, exc
            )
            return {}
