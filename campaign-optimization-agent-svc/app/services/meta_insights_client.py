"""SKL-COA-02: Meta Marketing API Insights fetcher.

Fetches campaign, ad set, and ad level insights from Meta Insights API.
Supports STUB MODE when META_ADS_SANDBOX_MODE=True (returns realistic fake data).
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.logic.circuit_breaker import get_breaker

logger = logging.getLogger(__name__)


@dataclass
class AdSetInsights:
    """Insights for a single ad set."""

    ad_set_id: str = ""
    ad_set_name: str = ""
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    ctr: float = 0.0
    cpm: float = 0.0
    frequency: float = 0.0
    reach: int = 0
    conversions: int = 0
    cost_per_action: float = 0.0
    purchase_roas: float = 0.0
    actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AdInsights:
    """Insights for a single ad."""

    ad_id: str = ""
    ad_name: str = ""
    ad_set_id: str = ""
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    ctr: float = 0.0
    cpm: float = 0.0
    frequency: float = 0.0
    reach: int = 0
    conversions: int = 0
    cost_per_action: float = 0.0
    purchase_roas: float = 0.0
    actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CampaignInsights:
    """Aggregated insights for a full campaign."""

    campaign_id: str = ""
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    ctr: float = 0.0
    cpm: float = 0.0
    frequency: float = 0.0
    reach: int = 0
    conversions: int = 0
    cost_per_action: float = 0.0
    purchase_roas: float = 0.0
    ad_sets: list[AdSetInsights] = field(default_factory=list)
    ads: list[AdInsights] = field(default_factory=list)
    date_start: str = ""
    date_stop: str = ""


class MetaInsightsClient:
    """Meta Marketing API Insights fetcher.

    Uses facebook-business SDK with asyncio.to_thread() wrapper.
    Falls back to stub data when META_ADS_SANDBOX_MODE=True.
    """

    def __init__(
        self,
        api_version: str = "v21.0",
        sandbox_mode: bool = True,
    ):
        self._api_version = api_version
        self._sandbox_mode = sandbox_mode
        self._breaker = get_breaker("meta_insights")

    async def fetch_campaign_insights(
        self,
        ad_account_id: str,
        campaign_id: str,
        access_token: str,
        date_preset: str = "last_7d",
    ) -> CampaignInsights:
        """Fetch campaign insights from Meta Insights API.

        Args:
            ad_account_id: Meta ad account ID (without act_ prefix).
            campaign_id: Meta campaign ID.
            access_token: Meta access token.
            date_preset: Date preset for the query.

        Returns:
            CampaignInsights with ad set and ad level breakdowns.
        """
        if self._sandbox_mode:
            return self._generate_stub_insights(campaign_id)

        if self._breaker.is_open:
            logger.warning(
                "Meta Insights circuit breaker OPEN — skipping %s",
                campaign_id,
            )
            return CampaignInsights(campaign_id=campaign_id)

        try:
            insights = await asyncio.to_thread(
                self._fetch_insights_sync,
                ad_account_id,
                campaign_id,
                access_token,
                date_preset,
            )
            self._breaker.record_success()
            return insights
        except Exception as exc:
            trip = self._breaker.record_failure()
            logger.error(
                "Meta Insights fetch failed for %s: %s", campaign_id, exc
            )
            if trip:
                logger.error(
                    "Circuit breaker tripped: %s", trip["action"]
                )
            return CampaignInsights(campaign_id=campaign_id)

    def _fetch_insights_sync(
        self,
        ad_account_id: str,
        campaign_id: str,
        access_token: str,
        date_preset: str,
    ) -> CampaignInsights:
        """Synchronous Meta API call (runs in thread pool).

        Uses facebook-business SDK for actual API calls.
        """
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount

        FacebookAdsApi.init(access_token=access_token)
        account = AdAccount(f"act_{ad_account_id}")

        fields = [
            "impressions",
            "clicks",
            "spend",
            "actions",
            "cost_per_action_type",
            "ctr",
            "frequency",
            "reach",
            "cpm",
            "purchase_roas",
        ]
        params = {
            "filtering": [
                {
                    "field": "campaign.id",
                    "operator": "EQUAL",
                    "value": campaign_id,
                }
            ],
            "date_preset": date_preset,
        }

        # Campaign-level insights
        campaign_data = account.get_insights(
            fields=fields,
            params={**params, "level": "campaign"},
        )

        # Ad set-level insights
        ad_set_data = account.get_insights(
            fields=fields,
            params={**params, "level": "adset"},
        )

        # Ad-level insights
        ad_data = account.get_insights(
            fields=fields,
            params={**params, "level": "ad"},
        )

        # Parse campaign level
        campaign_row = campaign_data[0] if campaign_data else {}
        result = CampaignInsights(
            campaign_id=campaign_id,
            impressions=int(campaign_row.get("impressions", 0)),
            clicks=int(campaign_row.get("clicks", 0)),
            spend=float(campaign_row.get("spend", 0)),
            ctr=float(campaign_row.get("ctr", 0)),
            cpm=float(campaign_row.get("cpm", 0)),
            frequency=float(campaign_row.get("frequency", 0)),
            reach=int(campaign_row.get("reach", 0)),
            date_start=campaign_row.get("date_start", ""),
            date_stop=campaign_row.get("date_stop", ""),
        )

        # Parse ad set level
        for row in ad_set_data:
            result.ad_sets.append(
                AdSetInsights(
                    ad_set_id=row.get("adset_id", ""),
                    ad_set_name=row.get("adset_name", ""),
                    impressions=int(row.get("impressions", 0)),
                    clicks=int(row.get("clicks", 0)),
                    spend=float(row.get("spend", 0)),
                    ctr=float(row.get("ctr", 0)),
                    cpm=float(row.get("cpm", 0)),
                    frequency=float(row.get("frequency", 0)),
                    reach=int(row.get("reach", 0)),
                    actions=row.get("actions", []),
                )
            )

        # Parse ad level
        for row in ad_data:
            result.ads.append(
                AdInsights(
                    ad_id=row.get("ad_id", ""),
                    ad_name=row.get("ad_name", ""),
                    ad_set_id=row.get("adset_id", ""),
                    impressions=int(row.get("impressions", 0)),
                    clicks=int(row.get("clicks", 0)),
                    spend=float(row.get("spend", 0)),
                    ctr=float(row.get("ctr", 0)),
                    cpm=float(row.get("cpm", 0)),
                    frequency=float(row.get("frequency", 0)),
                    reach=int(row.get("reach", 0)),
                    actions=row.get("actions", []),
                )
            )

        return result

    def _generate_stub_insights(
        self, campaign_id: str
    ) -> CampaignInsights:
        """Generate realistic stub insights for sandbox mode."""
        impressions = random.randint(5000, 50000)
        clicks = int(impressions * random.uniform(0.01, 0.05))
        spend = round(random.uniform(20, 200), 2)
        conversions = int(clicks * random.uniform(0.02, 0.15))

        ad_sets = []
        for i in range(random.randint(2, 4)):
            as_impressions = int(impressions * random.uniform(0.2, 0.4))
            as_clicks = int(as_impressions * random.uniform(0.01, 0.05))
            as_spend = round(spend * random.uniform(0.2, 0.4), 2)
            as_conversions = int(as_clicks * random.uniform(0.02, 0.15))
            ad_sets.append(
                AdSetInsights(
                    ad_set_id=f"stub_adset_{i}",
                    ad_set_name=f"Ad Set {i + 1}",
                    impressions=as_impressions,
                    clicks=as_clicks,
                    spend=as_spend,
                    ctr=round(as_clicks / max(as_impressions, 1) * 100, 2),
                    cpm=round(as_spend / max(as_impressions, 1) * 1000, 2),
                    frequency=round(random.uniform(1.0, 3.5), 2),
                    reach=int(as_impressions * 0.7),
                    conversions=as_conversions,
                    cost_per_action=(
                        round(as_spend / max(as_conversions, 1), 2)
                    ),
                    purchase_roas=round(random.uniform(0.5, 4.0), 2),
                )
            )

        ads = []
        for i, ad_set in enumerate(ad_sets):
            for j in range(random.randint(1, 3)):
                ad_imp = int(
                    ad_set.impressions * random.uniform(0.3, 0.6)
                )
                ad_clicks = int(ad_imp * random.uniform(0.01, 0.05))
                ad_spend = round(
                    ad_set.spend * random.uniform(0.3, 0.6), 2
                )
                ads.append(
                    AdInsights(
                        ad_id=f"stub_ad_{i}_{j}",
                        ad_name=f"Ad {i + 1}-{j + 1}",
                        ad_set_id=ad_set.ad_set_id,
                        impressions=ad_imp,
                        clicks=ad_clicks,
                        spend=ad_spend,
                        ctr=round(
                            ad_clicks / max(ad_imp, 1) * 100, 2
                        ),
                        cpm=round(
                            ad_spend / max(ad_imp, 1) * 1000, 2
                        ),
                        frequency=round(random.uniform(1.0, 3.0), 2),
                        reach=int(ad_imp * 0.7),
                    )
                )

        return CampaignInsights(
            campaign_id=campaign_id,
            impressions=impressions,
            clicks=clicks,
            spend=spend,
            ctr=round(clicks / max(impressions, 1) * 100, 2),
            cpm=round(spend / max(impressions, 1) * 1000, 2),
            frequency=round(random.uniform(1.0, 3.0), 2),
            reach=int(impressions * 0.7),
            conversions=conversions,
            cost_per_action=(
                round(spend / max(conversions, 1), 2)
            ),
            purchase_roas=round(random.uniform(0.5, 4.0), 2),
            ad_sets=ad_sets,
            ads=ads,
            date_start="2026-03-29",
            date_stop="2026-04-05",
        )
