"""Tests for NameScorer (SKL-NTA-10)."""

import pytest

from app.logic.name_scorer import NameScorer


@pytest.fixture
def scorer():
    return NameScorer()


class TestAvailabilityScore:
    """Test availability score computation."""

    def test_all_available(self, scorer):
        avail = {
            "domain_com": True,
            "domain_io": True,
            "domain_co": True,
            "twitter": True,
            "instagram": True,
            "linkedin": True,
            "trademark_clear": True,
        }
        score = scorer._compute_availability_score(avail)
        assert score == 100.0

    def test_all_taken(self, scorer):
        avail = {
            "domain_com": False,
            "domain_io": False,
            "domain_co": False,
            "twitter": False,
            "instagram": False,
            "linkedin": False,
            "trademark_clear": False,
        }
        score = scorer._compute_availability_score(avail)
        assert score == 0.0

    def test_domain_com_heaviest_weight(self, scorer):
        """domain_com has weight 30 vs 10 for other domains."""
        only_com = {
            "domain_com": True,
            "domain_io": False,
            "domain_co": False,
            "twitter": False,
            "instagram": False,
            "linkedin": False,
            "trademark_clear": False,
        }
        score = scorer._compute_availability_score(only_com)
        # 30 out of 100 → 30.0
        assert score == 30.0

    def test_trademark_weight(self, scorer):
        """Trademark clear has weight 20."""
        only_trademark = {
            "domain_com": False,
            "domain_io": False,
            "domain_co": False,
            "twitter": False,
            "instagram": False,
            "linkedin": False,
            "trademark_clear": True,
        }
        score = scorer._compute_availability_score(only_trademark)
        # 20 out of 100 → 20.0
        assert score == 20.0

    def test_no_data_returns_neutral(self, scorer):
        score = scorer._compute_availability_score({})
        assert score == 50.0

    def test_none_values_excluded_from_max(self, scorer):
        """None values (check failed) excluded from both score and max."""
        avail = {
            "domain_com": True,
            "domain_io": None,
            "twitter": None,
            "trademark_clear": True,
        }
        # max_score = 30 (com) + 20 (trademark) = 50
        # score = 30 + 20 = 50
        score = scorer._compute_availability_score(avail)
        assert score == 100.0


class TestOverallScore:
    """Test weighted overall score computation."""

    def test_all_100(self, scorer):
        scores = {
            "strategy_alignment": 100,
            "memorability": 100,
            "linguistic": 100,
            "availability": 100,
        }
        result = scorer._compute_overall(scores)
        assert result == 100.0

    def test_all_zero(self, scorer):
        scores = {
            "strategy_alignment": 0,
            "memorability": 0,
            "linguistic": 0,
            "availability": 0,
        }
        result = scorer._compute_overall(scores)
        assert result == 0.0

    def test_correct_weights(self, scorer):
        """Strategy 30%, memorability 25%, linguistic 25%, availability 20%."""
        scores = {
            "strategy_alignment": 100,
            "memorability": 0,
            "linguistic": 0,
            "availability": 0,
        }
        result = scorer._compute_overall(scores)
        assert result == 30.0

        scores["strategy_alignment"] = 0
        scores["memorability"] = 100
        result = scorer._compute_overall(scores)
        assert result == 25.0

        scores["memorability"] = 0
        scores["availability"] = 100
        result = scorer._compute_overall(scores)
        assert result == 20.0


class TestScoreAll:
    """Test score_all method."""

    def test_score_all_adds_overall(self, scorer):
        candidates = [
            {
                "name": "TestBrand",
                "scores": {
                    "linguistic": 80,
                    "memorability": 70,
                    "strategy_alignment": 90,
                },
                "availability": {
                    "domain_com": True,
                    "trademark_clear": True,
                },
            },
        ]
        result = scorer.score_all(candidates, {})
        assert "overall" in result[0]["scores"]
        assert "availability" in result[0]["scores"]
        assert result[0]["scores"]["overall"] > 0

    def test_score_all_defaults_missing_scores(self, scorer):
        candidates = [{"name": "Bare", "scores": {}, "availability": {}}]
        result = scorer.score_all(candidates, {})
        assert result[0]["scores"]["linguistic"] == 50.0
        assert result[0]["scores"]["memorability"] == 50.0
        assert result[0]["scores"]["strategy_alignment"] == 50.0


class TestSummarize:
    """Test scoring summary generation."""

    def test_empty_candidates(self, scorer):
        summary = scorer.summarize([])
        assert summary["total"] == 0

    def test_summary_statistics(self, scorer):
        candidates = [
            {"scores": {"overall": 80, "linguistic": 70, "memorability": 85, "availability": 90, "strategy_alignment": 75}},
            {"scores": {"overall": 60, "linguistic": 50, "memorability": 65, "availability": 70, "strategy_alignment": 55}},
        ]
        summary = scorer.summarize(candidates)
        assert summary["total"] == 2
        assert summary["avg_overall"] == 70.0
        assert summary["max_overall"] == 80.0
        assert summary["min_overall"] == 60.0
        assert summary["avg_linguistic"] == 60.0
