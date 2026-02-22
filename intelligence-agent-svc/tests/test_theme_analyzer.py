"""Tests for theme extraction and sentiment analysis."""

from app.logic.analysis.theme_analyzer import ThemeAnalyzer


class TestThemeExtraction:
    """Verify theme extraction from findings."""

    def setup_method(self):
        self.analyzer = ThemeAnalyzer()

    def test_extracts_market_position_theme(self):
        """Market position keywords trigger that theme."""
        findings = [
            "Company has strong market share and competitive positioning",
            "The brand is a market leader in the sector",
        ]
        themes = self.analyzer.extract_themes(findings)
        categories = [t["category"] for t in themes]
        assert "market_position" in categories

    def test_extracts_financial_theme(self):
        """Financial keywords trigger that theme."""
        findings = [
            "Revenue growth exceeded expectations at 15%",
            "Profit margins improved significantly",
        ]
        themes = self.analyzer.extract_themes(findings)
        categories = [t["category"] for t in themes]
        assert "financial_performance" in categories

    def test_extracts_brand_perception_theme(self):
        """Brand keywords trigger that theme."""
        findings = [
            "Brand awareness is high among target demographics",
            "Customer loyalty and trust metrics are strong",
        ]
        themes = self.analyzer.extract_themes(findings)
        categories = [t["category"] for t in themes]
        assert "brand_perception" in categories

    def test_extracts_innovation_theme(self):
        """Innovation keywords trigger that theme."""
        findings = [
            "Significant investment in technology and innovation",
            "Digital transformation driving product development",
        ]
        themes = self.analyzer.extract_themes(findings)
        categories = [t["category"] for t in themes]
        assert "innovation" in categories

    def test_no_findings_returns_empty(self):
        """Empty findings → no themes."""
        themes = self.analyzer.extract_themes([])
        assert themes == []

    def test_multiple_themes_sorted_by_count(self):
        """Themes sorted by finding count (most relevant first)."""
        findings = [
            "Revenue growth is strong",  # financial + positive
            "Profit margins improving",  # financial
            "Brand awareness is high",  # brand
        ]
        themes = self.analyzer.extract_themes(findings)
        if len(themes) >= 2:
            # First theme should have highest finding_count
            assert themes[0]["finding_count"] >= themes[-1]["finding_count"]

    def test_theme_has_expected_keys(self):
        """Each theme dict has category, keywords_found, sentiment, finding_count."""
        findings = ["Market share is growing with strong revenue"]
        themes = self.analyzer.extract_themes(findings)
        if themes:
            theme = themes[0]
            assert "category" in theme
            assert "keywords_found" in theme
            assert "sentiment" in theme
            assert "finding_count" in theme


class TestSentimentScoring:
    """Verify sentiment scoring (0-100 scale, 50=neutral)."""

    def setup_method(self):
        self.analyzer = ThemeAnalyzer()

    def test_positive_findings_above_50(self):
        """Positive keywords → sentiment above 50."""
        findings = [
            "Strong growth in all segments",
            "Excellent premium brand positioning",
            "Innovative and trusted brand",
        ]
        score = self.analyzer.calculate_sentiment_score(findings)
        assert score > 50

    def test_negative_findings_below_50(self):
        """Negative keywords → sentiment below 50."""
        findings = [
            "Decline in market share observed",
            "Poor brand recognition and weak loyalty",
            "Risk of erosion in key segments",
        ]
        score = self.analyzer.calculate_sentiment_score(findings)
        assert score < 50

    def test_neutral_findings_around_50(self):
        """No sentiment keywords → score around 50."""
        findings = [
            "The company operates in the consumer sector",
            "Products are available in multiple regions",
        ]
        score = self.analyzer.calculate_sentiment_score(findings)
        assert abs(score - 50) < 20  # Roughly neutral

    def test_empty_findings_returns_50(self):
        """Empty findings → neutral 50."""
        score = self.analyzer.calculate_sentiment_score([])
        assert score == 50.0

    def test_score_clamped_to_0_100(self):
        """Score should always be within [0, 100]."""
        extreme_positive = ["excellent strong growth premium leading"] * 10
        score = self.analyzer.calculate_sentiment_score(extreme_positive)
        assert 0 <= score <= 100

        extreme_negative = ["decline weak poor loss erosion threat"] * 10
        score = self.analyzer.calculate_sentiment_score(extreme_negative)
        assert 0 <= score <= 100
