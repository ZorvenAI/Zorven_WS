"""SKL-COA-07 (execution): Meta Management API writer.

Handles all write operations to Meta Marketing API:
- Update ad set status, budget, targeting
- Update campaign status
- Read-back entity for verification

STUB MODE when META_ADS_SANDBOX_MODE=True.
Uses facebook-business SDK with asyncio.to_thread() wrapper.
"""

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.logic.circuit_breaker import get_breaker

logger = logging.getLogger(__name__)


class MetaManagementClient:
    """Meta Marketing API writer for optimization actions."""

    def __init__(
        self,
        api_version: str = "v21.0",
        sandbox_mode: bool = True,
    ):
        self._api_version = api_version
        self._sandbox_mode = sandbox_mode
        self._breaker = get_breaker("meta_management")

    async def update_ad_set_status(
        self,
        ad_set_id: str,
        status: str,
        access_token: str,
    ) -> bool:
        """Update an ad set's status (ACTIVE, PAUSED, DELETED).

        Args:
            ad_set_id: Meta ad set ID.
            status: Target status.
            access_token: Meta access token.

        Returns:
            True if successful.
        """
        if self._sandbox_mode:
            logger.info(
                "[SANDBOX] Update ad set %s status -> %s",
                ad_set_id,
                status,
            )
            return True

        if self._breaker.is_open:
            logger.warning(
                "Meta Management circuit breaker OPEN -- "
                "skipping ad set status update"
            )
            return False

        try:
            result = await asyncio.to_thread(
                self._update_ad_set_status_sync,
                ad_set_id,
                status,
                access_token,
            )
            self._breaker.record_success()
            return result
        except Exception as exc:
            self._breaker.record_failure()
            logger.error(
                "Failed to update ad set %s status: %s", ad_set_id, exc
            )
            return False

    def _update_ad_set_status_sync(
        self, ad_set_id: str, status: str, access_token: str
    ) -> bool:
        """Synchronous ad set status update."""
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adset import AdSet

        FacebookAdsApi.init(access_token=access_token)
        ad_set = AdSet(ad_set_id)
        ad_set.api_update(params={}, fields=[], pending=False)
        ad_set[AdSet.Field.status] = status
        ad_set.remote_update()
        return True

    async def update_ad_set_budget(
        self,
        ad_set_id: str,
        daily_budget_cents: int,
        access_token: str,
    ) -> bool:
        """Update an ad set's daily budget (in cents).

        Args:
            ad_set_id: Meta ad set ID.
            daily_budget_cents: New daily budget in cents.
            access_token: Meta access token.

        Returns:
            True if successful.
        """
        if self._sandbox_mode:
            logger.info(
                "[SANDBOX] Update ad set %s budget -> %d cents",
                ad_set_id,
                daily_budget_cents,
            )
            return True

        if self._breaker.is_open:
            logger.warning(
                "Meta Management circuit breaker OPEN -- "
                "skipping budget update"
            )
            return False

        try:
            result = await asyncio.to_thread(
                self._update_ad_set_budget_sync,
                ad_set_id,
                daily_budget_cents,
                access_token,
            )
            self._breaker.record_success()
            return result
        except Exception as exc:
            self._breaker.record_failure()
            logger.error(
                "Failed to update ad set %s budget: %s", ad_set_id, exc
            )
            return False

    def _update_ad_set_budget_sync(
        self, ad_set_id: str, daily_budget_cents: int, access_token: str
    ) -> bool:
        """Synchronous ad set budget update."""
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adset import AdSet

        FacebookAdsApi.init(access_token=access_token)
        ad_set = AdSet(ad_set_id)
        ad_set[AdSet.Field.daily_budget] = daily_budget_cents
        ad_set.remote_update()
        return True

    async def update_ad_set_targeting(
        self,
        ad_set_id: str,
        targeting_spec: dict[str, Any],
        access_token: str,
    ) -> bool:
        """Update an ad set's targeting specification.

        Args:
            ad_set_id: Meta ad set ID.
            targeting_spec: Meta targeting spec dict.
            access_token: Meta access token.

        Returns:
            True if successful.
        """
        if self._sandbox_mode:
            logger.info(
                "[SANDBOX] Update ad set %s targeting", ad_set_id
            )
            return True

        if self._breaker.is_open:
            return False

        try:
            result = await asyncio.to_thread(
                self._update_targeting_sync,
                ad_set_id,
                targeting_spec,
                access_token,
            )
            self._breaker.record_success()
            return result
        except Exception as exc:
            self._breaker.record_failure()
            logger.error(
                "Failed to update ad set %s targeting: %s",
                ad_set_id,
                exc,
            )
            return False

    def _update_targeting_sync(
        self,
        ad_set_id: str,
        targeting_spec: dict[str, Any],
        access_token: str,
    ) -> bool:
        """Synchronous targeting update."""
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adset import AdSet

        FacebookAdsApi.init(access_token=access_token)
        ad_set = AdSet(ad_set_id)
        ad_set[AdSet.Field.targeting] = targeting_spec
        ad_set.remote_update()
        return True

    async def update_campaign_status(
        self,
        campaign_id: str,
        status: str,
        access_token: str,
    ) -> bool:
        """Update a campaign's status.

        Args:
            campaign_id: Meta campaign ID.
            status: Target status.
            access_token: Meta access token.

        Returns:
            True if successful.
        """
        if self._sandbox_mode:
            logger.info(
                "[SANDBOX] Update campaign %s status -> %s",
                campaign_id,
                status,
            )
            return True

        if self._breaker.is_open:
            return False

        try:
            result = await asyncio.to_thread(
                self._update_campaign_status_sync,
                campaign_id,
                status,
                access_token,
            )
            self._breaker.record_success()
            return result
        except Exception as exc:
            self._breaker.record_failure()
            logger.error(
                "Failed to update campaign %s status: %s",
                campaign_id,
                exc,
            )
            return False

    def _update_campaign_status_sync(
        self, campaign_id: str, status: str, access_token: str
    ) -> bool:
        """Synchronous campaign status update."""
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.campaign import Campaign

        FacebookAdsApi.init(access_token=access_token)
        campaign = Campaign(campaign_id)
        campaign[Campaign.Field.status] = status
        campaign.remote_update()
        return True

    async def read_back_entity(
        self,
        entity_type: str,
        entity_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        """Read back an entity from Meta API for verification.

        Args:
            entity_type: One of 'campaign', 'ad_set', 'ad'.
            entity_id: Meta entity ID.
            access_token: Meta access token.

        Returns:
            Entity data dict from Meta API.
        """
        if self._sandbox_mode:
            logger.info(
                "[SANDBOX] Read back %s %s", entity_type, entity_id
            )
            return {
                "id": entity_id,
                "entity_type": entity_type,
                "status": "ACTIVE",
                "sandbox": True,
            }

        try:
            result = await asyncio.to_thread(
                self._read_back_sync,
                entity_type,
                entity_id,
                access_token,
            )
            return result
        except Exception as exc:
            logger.error(
                "Failed to read back %s %s: %s",
                entity_type,
                entity_id,
                exc,
            )
            return {}

    def _read_back_sync(
        self, entity_type: str, entity_id: str, access_token: str
    ) -> dict[str, Any]:
        """Synchronous entity read-back."""
        from facebook_business.api import FacebookAdsApi

        FacebookAdsApi.init(access_token=access_token)

        if entity_type == "campaign":
            from facebook_business.adobjects.campaign import Campaign

            entity = Campaign(entity_id)
            entity.remote_read(fields=["status", "daily_budget", "name"])
            return dict(entity)
        elif entity_type == "ad_set":
            from facebook_business.adobjects.adset import AdSet

            entity = AdSet(entity_id)
            entity.remote_read(
                fields=["status", "daily_budget", "targeting", "name"]
            )
            return dict(entity)
        elif entity_type == "ad":
            from facebook_business.adobjects.ad import Ad

            entity = Ad(entity_id)
            entity.remote_read(fields=["status", "name"])
            return dict(entity)
        else:
            logger.warning("Unknown entity type: %s", entity_type)
            return {}
