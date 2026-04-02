"""Tests for the rollback manager."""

import pytest
from unittest.mock import AsyncMock

from app.logic.rollback import RollbackManager


class TestRollbackManager:
    def setup_method(self):
        self.mgr = RollbackManager()

    def test_track_entities(self):
        self.mgr.track("campaign", "c1")
        self.mgr.track("ad_set", "as1")
        self.mgr.track("ad", "a1")
        assert len(self.mgr.entities) == 3

    async def test_rollback_all(self):
        self.mgr.track("campaign", "c1")
        self.mgr.track("ad_set", "as1")
        mock_meta = AsyncMock()
        mock_meta.pause_entities = AsyncMock(
            return_value=[
                {"id": "as1", "type": "ad_set", "paused": True},
                {"id": "c1", "type": "campaign", "paused": True},
            ]
        )
        result = await self.mgr.rollback_all(mock_meta, "test failure")
        assert result["rolled_back"] == 2
        assert result["reason"] == "test failure"

    async def test_rollback_empty(self):
        mock_meta = AsyncMock()
        result = await self.mgr.rollback_all(mock_meta, "no entities")
        assert result["rolled_back"] == 0

    async def test_only_pausable_entities_rolled_back(self):
        """Ads and creatives are not individually paused."""
        self.mgr.track("campaign", "c1")
        self.mgr.track("ad_set", "as1")
        self.mgr.track("ad", "a1")
        self.mgr.track("creative", "cr1")

        mock_meta = AsyncMock()
        mock_meta.pause_entities = AsyncMock(return_value=[])

        await self.mgr.rollback_all(mock_meta, "test")
        # Only campaign and ad_set should be passed to pause
        call_args = mock_meta.pause_entities.call_args[0][0]
        types = {e["type"] for e in call_args}
        assert types == {"campaign", "ad_set"}

    def test_clear(self):
        self.mgr.track("campaign", "c1")
        self.mgr.clear()
        assert len(self.mgr.entities) == 0
