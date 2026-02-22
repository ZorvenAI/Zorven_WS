"""Tests for competitive gap analysis."""

from app.logic.analysis.competitive_gap import CompetitiveGapAnalyzer


class TestCompetitiveGapAnalyzer:
    """Validate gap analysis from discovery findings."""

    def setup_method(self):
        self.analyzer = CompetitiveGapAnalyzer()

    async def test_rule_based_with_strengths(self):
        """Findings with strength keywords → categorized as strengths."""
        previous_outputs = {
            "discovery": {
                "findings": [
                    "Company is the market leader in premium brands",
                    "Strong growth in digital channels",
                    "Innovative product development pipeline",
                ]
            }
        }
        result = await self.analyzer.analyze(
            previous_outputs=previous_outputs,
            config={},
        )
        assert len(result["strengths"]) > 0
        assert "market_opportunities" in result

    async def test_rule_based_with_gaps(self):
        """Findings with gap keywords → categorized as gaps."""
        previous_outputs = {
            "discovery": {
                "findings": [
                    "Significant gap in e-commerce presence",
                    "Trailing behind competitors in social media",
                    "Decline in brand awareness among youth",
                ]
            }
        }
        result = await self.analyzer.analyze(
            previous_outputs=previous_outputs,
            config={},
        )
        assert len(result["gaps"]) > 0
        assert len(result["market_opportunities"]) > 0

    async def test_no_discovery_data(self):
        """No upstream data → warning gaps message."""
        result = await self.analyzer.analyze(
            previous_outputs={},
            config={},
        )
        assert len(result["gaps"]) > 0
        assert "Insufficient" in result["gaps"][0]

    async def test_mixed_findings(self):
        """Mixed findings get categorized correctly."""
        previous_outputs = {
            "research": {
                "findings": [
                    "Leading brand in the market",
                    "Gap in customer retention strategies",
                    "Average performance metrics",
                ]
            }
        }
        result = await self.analyzer.analyze(
            previous_outputs=previous_outputs,
            config={},
        )
        assert "strengths" in result
        assert "gaps" in result
        assert "weaknesses" in result

    async def test_extracts_from_raw_context(self):
        """Raw context paragraphs are also analyzed."""
        previous_outputs = {
            "research": {
                "findings": [],
                "raw_context": (
                    "The company is a dominant force in the market.\n\n"
                    "However, there is a significant gap in their "
                    "digital transformation strategy."
                ),
            }
        }
        result = await self.analyzer.analyze(
            previous_outputs=previous_outputs,
            config={},
        )
        # Should have extracted from raw_context paragraphs
        total = (
            len(result["strengths"]) + len(result["gaps"]) + len(result["weaknesses"])
        )
        assert total > 0

    async def test_returns_all_expected_keys(self):
        """Result dict always has strengths, weaknesses, gaps, market_opportunities."""
        result = await self.analyzer.analyze(
            previous_outputs={"d": {"findings": ["some finding"]}},
            config={},
        )
        assert "strengths" in result
        assert "weaknesses" in result
        assert "gaps" in result
        assert "market_opportunities" in result
