"""Tests for StrategySynthesizer logic module."""

import pytest

from app.logic.strategy_synthesizer import StrategySynthesizer


@pytest.fixture
def synthesizer():
    return StrategySynthesizer()


class TestStrategySynthesizer:

    async def test_synthesize_extracts_strategy(self, synthesizer):
        llm_result = {
            "strategy": {
                "executive_summary": "Adopt hybrid architecture",
                "implementation_guidelines": ["Phase 1: Audit"],
            }
        }
        result = await synthesizer.synthesize(llm_result)
        assert result["executive_summary"] == "Adopt hybrid architecture"

    async def test_synthesize_empty(self, synthesizer):
        result = await synthesizer.synthesize({})
        assert result == {}
