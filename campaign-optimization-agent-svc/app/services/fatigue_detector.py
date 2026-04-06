"""SKL-COA-04: Creative fatigue detection.

Tracks per-ad CTR over rolling 3-day windows vs peak.
Flags when decline exceeds fatigue_ctr_decline_threshold_pct.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FatiguedAd:
    """An ad flagged for creative fatigue."""

    ad_id: str = ""
    ad_name: str = ""
    ad_set_id: str = ""
    ctr_current: float = 0.0
    ctr_peak: float = 0.0
    decline_pct: float = 0.0
    frequency: float = 0.0
    days_running: int = 0
    confidence: str = "LOW"  # HIGH, MEDIUM, LOW


@dataclass
class FatigueReport:
    """Report of creative fatigue across a campaign."""

    campaign_id: str = ""
    fatigued_ads: list[FatiguedAd] = field(default_factory=list)
    total_ads_analyzed: int = 0
    fatigue_rate: float = 0.0


class FatigueDetector:
    """Detects creative fatigue based on CTR decline from peak."""

    def __init__(self):
        self._threshold_pct = settings.FATIGUE_CTR_DECLINE_THRESHOLD_PCT

    async def detect_fatigue(
        self,
        campaign_id: str,
        ad_insights: list[Any],
        ctr_peaks: dict[str, float],
        config: dict[str, Any],
    ) -> FatigueReport:
        """Detect creative fatigue across all ads in a campaign.

        Args:
            campaign_id: Campaign identifier.
            ad_insights: List of AdInsights dataclasses.
            ctr_peaks: Dict mapping ad_id -> peak CTR value.
            config: Tenant optimization config (may override threshold).

        Returns:
            FatigueReport with list of fatigued ads.
        """
        threshold = config.get(
            "fatigue_ctr_decline_threshold_pct", self._threshold_pct
        )
        fatigued = []

        for ad in ad_insights:
            ad_id = ad.ad_id
            current_ctr = ad.ctr
            peak_ctr = ctr_peaks.get(ad_id, current_ctr)

            # Update peak if current is higher
            if current_ctr > peak_ctr:
                peak_ctr = current_ctr

            # Calculate decline
            if peak_ctr > 0:
                decline_pct = (
                    (peak_ctr - current_ctr) / peak_ctr * 100
                )
            else:
                decline_pct = 0

            if decline_pct >= threshold:
                # Determine confidence
                frequency = ad.frequency
                days_running = config.get(
                    f"ad_days_running_{ad_id}", 0
                )

                if (
                    decline_pct >= threshold
                    and frequency > 2.5
                    and days_running > 14
                ):
                    confidence = "HIGH"
                elif (
                    decline_pct >= threshold
                    and (frequency > 2.5 or days_running > 7)
                ):
                    confidence = "MEDIUM"
                else:
                    confidence = "LOW"

                fatigued.append(
                    FatiguedAd(
                        ad_id=ad_id,
                        ad_name=ad.ad_name,
                        ad_set_id=ad.ad_set_id,
                        ctr_current=current_ctr,
                        ctr_peak=peak_ctr,
                        decline_pct=round(decline_pct, 1),
                        frequency=frequency,
                        days_running=days_running,
                        confidence=confidence,
                    )
                )

        total = len(ad_insights)
        rate = len(fatigued) / max(total, 1) * 100

        if fatigued:
            logger.info(
                "Fatigue detected in campaign %s: %d/%d ads (%.0f%%)",
                campaign_id,
                len(fatigued),
                total,
                rate,
            )

        return FatigueReport(
            campaign_id=campaign_id,
            fatigued_ads=fatigued,
            total_ads_analyzed=total,
            fatigue_rate=round(rate, 1),
        )
