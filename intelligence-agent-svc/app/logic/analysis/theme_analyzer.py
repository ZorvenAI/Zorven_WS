"""
Theme extraction and sentiment analysis from text findings.

Uses keyword-based scoring for rule-based mode.
Can be enhanced with Gemini for richer NLP analysis.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Positive sentiment keywords (weighted)
POSITIVE_KEYWORDS: dict[str, float] = {
    "strong": 1.0,
    "growth": 1.0,
    "premium": 1.2,
    "leading": 1.2,
    "innovative": 1.0,
    "trusted": 1.0,
    "positive": 0.8,
    "excellent": 1.2,
    "robust": 1.0,
    "increase": 0.8,
    "improve": 0.8,
    "success": 1.0,
    "dominant": 1.0,
}

# Negative sentiment keywords (weighted)
NEGATIVE_KEYWORDS: dict[str, float] = {
    "decline": -1.0,
    "weak": -1.0,
    "risk": -0.8,
    "loss": -1.0,
    "poor": -1.2,
    "negative": -0.8,
    "threat": -0.8,
    "volatile": -0.6,
    "erosion": -1.0,
    "behind": -0.8,
    "decrease": -0.8,
    "challenge": -0.6,
}

# Theme categories and their trigger keywords
THEME_CATEGORIES: dict[str, list[str]] = {
    "market_position": [
        "market share",
        "market position",
        "competitive",
        "leader",
        "ranking",
        "positioning",
    ],
    "financial_performance": [
        "revenue",
        "profit",
        "margin",
        "growth rate",
        "earnings",
        "financial",
        "sales",
    ],
    "brand_perception": [
        "brand",
        "awareness",
        "loyalty",
        "sentiment",
        "reputation",
        "perception",
        "trust",
    ],
    "innovation": [
        "innovation",
        "technology",
        "digital",
        "R&D",
        "patent",
        "product development",
    ],
    "regulatory": [
        "regulation",
        "compliance",
        "legal",
        "trademark",
        "patent",
        "intellectual property",
    ],
}


class ThemeAnalyzer:
    """Extract themes and sentiment polarity from text findings."""

    def extract_themes(self, findings: list[str]) -> list[dict[str, Any]]:
        """
        Extract key themes with sentiment scores from findings.

        Returns a list of theme dicts:
          {category, keywords_found, sentiment, finding_count}
        """
        if not findings:
            return []

        combined_text = " ".join(findings).lower()
        themes: list[dict[str, Any]] = []

        for category, keywords in THEME_CATEGORIES.items():
            found_keywords = [kw for kw in keywords if kw in combined_text]
            if found_keywords:
                # Count findings mentioning this theme
                relevant_findings = [
                    f for f in findings if any(kw in f.lower() for kw in keywords)
                ]
                sentiment = self._sentiment_for_texts(relevant_findings)

                themes.append(
                    {
                        "category": category,
                        "keywords_found": found_keywords,
                        "sentiment": round(sentiment, 1),
                        "finding_count": len(relevant_findings),
                    }
                )

        # Sort by finding count (most relevant first)
        themes.sort(key=lambda t: t["finding_count"], reverse=True)

        logger.info("Extracted %d themes from %d findings", len(themes), len(findings))
        return themes

    def calculate_sentiment_score(self, findings: list[str]) -> float:
        """
        Aggregate sentiment score (0–100) from findings text.

        50 = neutral, >50 = positive, <50 = negative.
        """
        if not findings:
            return 50.0

        return self._sentiment_for_texts(findings)

    def _sentiment_for_texts(self, texts: list[str]) -> float:
        """Calculate sentiment score for a list of texts."""
        if not texts:
            return 50.0

        total_score = 0.0
        total_weight = 0.0

        for text in texts:
            words = re.findall(r"\w+", text.lower())
            text_score = 0.0

            for word in words:
                if word in POSITIVE_KEYWORDS:
                    text_score += POSITIVE_KEYWORDS[word]
                elif word in NEGATIVE_KEYWORDS:
                    text_score += NEGATIVE_KEYWORDS[word]

            total_score += text_score
            total_weight += 1.0

        if total_weight == 0:
            return 50.0

        # Normalize: map raw score to 0-100 range
        avg_score = total_score / total_weight
        # Clamp to roughly [-3, +3] range and map to 0-100
        normalized = 50.0 + (avg_score / 3.0) * 50.0
        return max(0.0, min(100.0, normalized))
