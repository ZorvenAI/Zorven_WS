"""Tests for SKL-COA-04: Creative fatigue detection.

Tests CTR decline detection, confidence levels, peak tracking,
and rolling window behavior.
"""

import pytest
from unittest.mock import MagicMock

from app.services.fatigue_detector import (
    FatigueDetector,
    FatigueReport,
    FatiguedAd,
)
from app.services.meta_insights_client import AdInsights


@pytest.fixture
def detector():
    return FatigueDetector()


def _make_ad(ad_id="ad_001", ctr=3.0, frequency=1.5):
    return AdInsights(
        ad_id=ad_id,
        ad_name=f"Ad {ad_id}",
        ad_set_id="adset_001",
        impressions=10000,
        clicks=int(10000 * ctr / 100),
        spend=100.0,
        ctr=ctr,
        frequency=frequency,
    )


# ── Fatigue Detection ────────────────────────────────────────────


class TestFatigueDetection:
    @pytest.mark.asyncio
    async def test_no_fatigue_when_ctr_at_peak(self, detector):
        """No fatigue flagged when current CTR equals peak."""
        ads = [_make_ad(ctr=3.0)]
        peaks = {"ad_001": 3.0}
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {}
        )
        assert len(report.fatigued_ads) == 0
        assert report.fatigue_rate == 0.0

    @pytest.mark.asyncio
    async def test_fatigue_when_ctr_declines_above_threshold(self, detector):
        """Fatigue flagged when CTR decline >= 20% from peak."""
        ads = [_make_ad(ad_id="ad_001", ctr=2.0)]
        peaks = {"ad_001": 4.0}  # 50% decline
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {}
        )
        assert len(report.fatigued_ads) == 1
        assert report.fatigued_ads[0].decline_pct == 50.0

    @pytest.mark.asyncio
    async def test_no_fatigue_slight_decline(self, detector):
        """No fatigue when decline < threshold (20%)."""
        ads = [_make_ad(ctr=3.5)]
        peaks = {"ad_001": 4.0}  # 12.5% decline
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {}
        )
        assert len(report.fatigued_ads) == 0

    @pytest.mark.asyncio
    async def test_peak_updated_when_current_higher(self, detector):
        """Peak CTR is updated if current exceeds stored peak."""
        ads = [_make_ad(ctr=5.0)]
        peaks = {"ad_001": 3.0}  # Current > peak => no decline
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {}
        )
        assert len(report.fatigued_ads) == 0

    @pytest.mark.asyncio
    async def test_new_ad_no_peak_history(self, detector):
        """New ad without peak history uses current as peak (no fatigue)."""
        ads = [_make_ad(ctr=3.0)]
        peaks = {}
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {}
        )
        assert len(report.fatigued_ads) == 0

    @pytest.mark.asyncio
    async def test_zero_peak_no_division_error(self, detector):
        """Peak CTR of 0 should not cause division by zero."""
        ads = [_make_ad(ctr=0.0)]
        peaks = {"ad_001": 0.0}
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {}
        )
        assert len(report.fatigued_ads) == 0


# ── Confidence Levels ────────────────────────────────────────────


class TestConfidenceLevels:
    @pytest.mark.asyncio
    async def test_high_confidence(self, detector):
        """HIGH: decline >= threshold + frequency > 2.5 + days > 14."""
        ads = [_make_ad(ctr=2.0, frequency=3.0)]
        peaks = {"ad_001": 4.0}
        config = {"ad_days_running_ad_001": 20}
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, config
        )
        assert report.fatigued_ads[0].confidence == "HIGH"

    @pytest.mark.asyncio
    async def test_medium_confidence_high_frequency(self, detector):
        """MEDIUM: decline >= threshold + frequency > 2.5 (days <= 14)."""
        ads = [_make_ad(ctr=2.0, frequency=3.0)]
        peaks = {"ad_001": 4.0}
        config = {"ad_days_running_ad_001": 5}
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, config
        )
        assert report.fatigued_ads[0].confidence == "MEDIUM"

    @pytest.mark.asyncio
    async def test_medium_confidence_long_running(self, detector):
        """MEDIUM: decline >= threshold + days > 7 (frequency <= 2.5)."""
        ads = [_make_ad(ctr=2.0, frequency=2.0)]
        peaks = {"ad_001": 4.0}
        config = {"ad_days_running_ad_001": 10}
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, config
        )
        assert report.fatigued_ads[0].confidence == "MEDIUM"

    @pytest.mark.asyncio
    async def test_low_confidence(self, detector):
        """LOW: decline >= threshold but frequency <= 2.5 and days <= 7."""
        ads = [_make_ad(ctr=2.0, frequency=1.5)]
        peaks = {"ad_001": 4.0}
        config = {"ad_days_running_ad_001": 3}
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, config
        )
        assert report.fatigued_ads[0].confidence == "LOW"


# ── Fatigue Rate ─────────────────────────────────────────────────


class TestFatigueRate:
    @pytest.mark.asyncio
    async def test_fatigue_rate_calculation(self, detector):
        """Fatigue rate = fatigued / total * 100."""
        ads = [
            _make_ad(ad_id="ad_001", ctr=2.0),
            _make_ad(ad_id="ad_002", ctr=3.5),
            _make_ad(ad_id="ad_003", ctr=1.5),
        ]
        peaks = {"ad_001": 4.0, "ad_002": 4.0, "ad_003": 4.0}
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {}
        )
        # ad_001 = 50% decline, ad_002 = 12.5% (no), ad_003 = 62.5% decline
        assert report.total_ads_analyzed == 3
        assert len(report.fatigued_ads) == 2
        expected_rate = round(2 / 3 * 100, 1)
        assert report.fatigue_rate == expected_rate

    @pytest.mark.asyncio
    async def test_fatigue_rate_zero_ads(self, detector):
        """Empty ad list returns 0 fatigue rate."""
        report = await detector.detect_fatigue(
            "camp_001", [], {}, {}
        )
        assert report.total_ads_analyzed == 0
        assert report.fatigue_rate == 0.0


# ── Custom Threshold ─────────────────────────────────────────────


class TestCustomThreshold:
    @pytest.mark.asyncio
    async def test_custom_threshold_from_config(self, detector):
        """Tenant can override fatigue threshold via config."""
        ads = [_make_ad(ctr=3.5)]
        peaks = {"ad_001": 4.0}  # 12.5% decline

        # Default threshold (20%) -> no fatigue
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {}
        )
        assert len(report.fatigued_ads) == 0

        # Custom 10% threshold -> fatigue detected
        report = await detector.detect_fatigue(
            "camp_001", ads, peaks, {"fatigue_ctr_decline_threshold_pct": 10}
        )
        assert len(report.fatigued_ads) == 1
