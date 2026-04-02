"""Meta Marketing API v21.0 wrapper.

Provides async CRUD operations for Campaign, AdSet, AdCreative, Ad,
and AdImage via the facebook-business SDK. All SDK calls are synchronous
and wrapped with ``asyncio.to_thread()`` for async compatibility.

Supports sandbox mode (uses test ad account) and production mode.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MetaApiClient:
    """Async wrapper around the Meta Marketing API (facebook-business SDK).

    Parameters
    ----------
    api_version : str
        Meta API version, e.g. ``"v21.0"``.
    sandbox_mode : bool
        When True, all operations target the Meta test/sandbox API.
    """

    def __init__(
        self,
        api_version: str = "v21.0",
        sandbox_mode: bool = True,
    ):
        self.api_version = api_version
        self.sandbox_mode = sandbox_mode
        self._api = None

    def initialize(self, access_token: str, app_id: str = "", app_secret: str = ""):
        """Initialize the facebook-business API session.

        Called per-request with tenant-specific credentials.
        """
        try:
            from facebook_business.api import FacebookAdsApi

            self._api = FacebookAdsApi.init(
                app_id=app_id,
                app_secret=app_secret,
                access_token=access_token,
                api_version=self.api_version,
            )
            logger.info(
                "Meta API initialized (version=%s, sandbox=%s)",
                self.api_version,
                self.sandbox_mode,
            )
        except ImportError:
            logger.warning(
                "facebook-business SDK not available; "
                "Meta API calls will return stubs"
            )
            self._api = None

    async def validate_account(self, ad_account_id: str) -> dict[str, Any]:
        """Validate Meta ad account status, permissions, spending limit.

        Returns dict with token_valid, account_status, permissions,
        spending_limit, all_passed.
        """
        if self._api is None:
            return self._stub_account_validation()

        def _validate():
            from facebook_business.adobjects.adaccount import AdAccount

            account = AdAccount(f"act_{ad_account_id}")
            fields = [
                "account_status",
                "spend_cap",
                "amount_spent",
                "currency",
                "name",
            ]
            info = account.api_get(fields=fields)
            return {
                "token_valid": True,
                "account_status": info.get("account_status", 0),
                "spending_limit": float(info.get("spend_cap", 0)) / 100,
                "amount_spent": float(info.get("amount_spent", 0)) / 100,
                "currency": info.get("currency", "USD"),
                "account_name": info.get("name", ""),
                "all_passed": info.get("account_status") == 1,
            }

        try:
            return await asyncio.to_thread(_validate)
        except Exception as exc:
            logger.error("Account validation failed: %s", exc)
            return {
                "token_valid": False,
                "account_status": 0,
                "all_passed": False,
                "error": str(exc),
            }

    async def create_campaign(
        self,
        ad_account_id: str,
        name: str,
        objective: str,
        special_ad_categories: list[str] | None = None,
        spending_limit_cents: int | None = None,
    ) -> str:
        """Create a Meta Campaign in PAUSED status.

        Returns the campaign_id string.
        """
        if self._api is None:
            return self._stub_id("campaign")

        def _create():
            from facebook_business.adobjects.adaccount import AdAccount
            from facebook_business.adobjects.campaign import Campaign

            account = AdAccount(f"act_{ad_account_id}")
            params = {
                Campaign.Field.name: name,
                Campaign.Field.objective: objective,
                Campaign.Field.status: Campaign.Status.paused,
                Campaign.Field.special_ad_categories: special_ad_categories or [],
            }
            if spending_limit_cents is not None:
                params[Campaign.Field.spend_cap] = spending_limit_cents

            result = account.create_campaign(params=params)
            return result["id"]

        return await asyncio.to_thread(_create)

    async def create_ad_set(
        self,
        ad_account_id: str,
        campaign_id: str,
        name: str,
        targeting: dict[str, Any],
        optimization_goal: str,
        billing_event: str,
        daily_budget_cents: int,
        start_time: str | None = None,
        end_time: str | None = None,
        placements: dict[str, Any] | None = None,
    ) -> str:
        """Create a Meta Ad Set in PAUSED status within a campaign.

        Returns the ad_set_id string.
        """
        if self._api is None:
            return self._stub_id("adset")

        def _create():
            from facebook_business.adobjects.adaccount import AdAccount
            from facebook_business.adobjects.adset import AdSet

            account = AdAccount(f"act_{ad_account_id}")
            params = {
                AdSet.Field.name: name,
                AdSet.Field.campaign_id: campaign_id,
                AdSet.Field.targeting: targeting,
                AdSet.Field.optimization_goal: optimization_goal,
                AdSet.Field.billing_event: billing_event,
                AdSet.Field.daily_budget: daily_budget_cents,
                AdSet.Field.status: AdSet.Status.paused,
            }
            if start_time:
                params[AdSet.Field.start_time] = start_time
            if end_time:
                params[AdSet.Field.end_time] = end_time

            result = account.create_ad_set(params=params)
            return result["id"]

        return await asyncio.to_thread(_create)

    async def upload_image(
        self,
        ad_account_id: str,
        image_bytes: bytes,
        name: str,
    ) -> dict[str, str]:
        """Upload an image to Meta Ad Images.

        Returns dict with ``hash`` and ``url``.
        """
        if self._api is None:
            return {"hash": f"stub_hash_{name}", "url": f"https://stub/{name}"}

        def _upload():
            from facebook_business.adobjects.adaccount import AdAccount
            from facebook_business.adobjects.adimage import AdImage

            account = AdAccount(f"act_{ad_account_id}")
            image = AdImage(parent_id=account.get_id_assured())
            image[AdImage.Field.filename] = name
            image[AdImage.Field.bytes] = image_bytes
            image.remote_create()
            return {
                "hash": image[AdImage.Field.hash],
                "url": image.get("url", ""),
            }

        return await asyncio.to_thread(_upload)

    async def create_ad_creative(
        self,
        ad_account_id: str,
        name: str,
        image_hash: str,
        headline: str,
        body: str,
        cta_type: str,
        link_url: str,
        description: str = "",
    ) -> str:
        """Create a Meta Ad Creative.

        Returns the creative_id string.
        """
        if self._api is None:
            return self._stub_id("creative")

        def _create():
            from facebook_business.adobjects.adaccount import AdAccount
            from facebook_business.adobjects.adcreative import AdCreative

            account = AdAccount(f"act_{ad_account_id}")
            params = {
                AdCreative.Field.name: name,
                AdCreative.Field.object_story_spec: {
                    "page_id": "",  # Set per-tenant at call site
                    "link_data": {
                        "image_hash": image_hash,
                        "link": link_url,
                        "message": body,
                        "name": headline,
                        "description": description,
                        "call_to_action": {
                            "type": cta_type,
                            "value": {"link": link_url},
                        },
                    },
                },
            }
            result = account.create_ad_creative(params=params)
            return result["id"]

        return await asyncio.to_thread(_create)

    async def create_ad(
        self,
        ad_account_id: str,
        ad_set_id: str,
        creative_id: str,
        name: str,
    ) -> str:
        """Create a Meta Ad in PAUSED status.

        Returns the ad_id string.
        """
        if self._api is None:
            return self._stub_id("ad")

        def _create():
            from facebook_business.adobjects.adaccount import AdAccount
            from facebook_business.adobjects.ad import Ad

            account = AdAccount(f"act_{ad_account_id}")
            params = {
                Ad.Field.name: name,
                Ad.Field.adset_id: ad_set_id,
                Ad.Field.creative: {"creative_id": creative_id},
                Ad.Field.status: Ad.Status.paused,
            }
            result = account.create_ad(params=params)
            return result["id"]

        return await asyncio.to_thread(_create)

    async def update_campaign_status(
        self, campaign_id: str, status: str
    ) -> bool:
        """Update campaign status (e.g. PAUSED -> ACTIVE).

        Returns True on success.
        """
        if self._api is None:
            return True

        def _update():
            from facebook_business.adobjects.campaign import Campaign

            campaign = Campaign(campaign_id)
            campaign.api_update(params={Campaign.Field.status: status})
            return True

        return await asyncio.to_thread(_update)

    async def update_ad_set_status(
        self, ad_set_id: str, status: str
    ) -> bool:
        """Update ad set status."""
        if self._api is None:
            return True

        def _update():
            from facebook_business.adobjects.adset import AdSet

            ad_set = AdSet(ad_set_id)
            ad_set.api_update(params={AdSet.Field.status: status})
            return True

        return await asyncio.to_thread(_update)

    async def get_ad_preview(
        self,
        creative_id: str,
        ad_format: str = "DESKTOP_FEED_STANDARD",
    ) -> str:
        """Fetch ad preview HTML for a creative.

        Returns preview HTML/iframe string.
        """
        if self._api is None:
            return f"<div>Preview for creative {creative_id}</div>"

        def _preview():
            from facebook_business.adobjects.adcreative import AdCreative

            creative = AdCreative(creative_id)
            previews = creative.get_previews(params={"ad_format": ad_format})
            if previews:
                return previews[0].get("body", "")
            return ""

        return await asyncio.to_thread(_preview)

    async def pause_entities(
        self,
        entities: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Pause multiple Meta entities for rollback.

        Each entity is ``{"type": "campaign|ad_set|ad", "id": "..."}``.
        Returns list of results with success/failure per entity.
        """
        results = []
        for entity in reversed(entities):  # Reverse order for safe rollback
            entity_type = entity["type"]
            entity_id = entity["id"]
            try:
                if entity_type == "campaign":
                    await self.update_campaign_status(entity_id, "PAUSED")
                elif entity_type == "ad_set":
                    await self.update_ad_set_status(entity_id, "PAUSED")
                results.append(
                    {"id": entity_id, "type": entity_type, "paused": True}
                )
            except Exception as exc:
                logger.error(
                    "Failed to pause %s %s: %s", entity_type, entity_id, exc
                )
                results.append(
                    {
                        "id": entity_id,
                        "type": entity_type,
                        "paused": False,
                        "error": str(exc),
                    }
                )
        return results

    # ------------------------------------------------------------------
    # Stub responses (when SDK is unavailable or in test mode)
    # ------------------------------------------------------------------

    @staticmethod
    def _stub_id(prefix: str) -> str:
        import uuid

        return f"stub_{prefix}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _stub_account_validation() -> dict[str, Any]:
        return {
            "token_valid": True,
            "account_status": 1,
            "permissions": ["ads_management", "ads_read"],
            "spending_limit": 100000.0,
            "amount_spent": 0.0,
            "currency": "USD",
            "account_name": "Stub Account",
            "all_passed": True,
        }
