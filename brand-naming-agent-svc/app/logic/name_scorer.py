"""SKL-NTA-10: Multi-dimensional scoring for name candidates."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NameScorer:
    """Score name candidates across multiple dimensions."""

    def score_all(
        self,
        candidates: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Score all candidates, adding availability dimension.

        Candidates already have linguistic, memorability, strategy_alignment
        scores from Claude. This method adds availability scoring and computes
        overall score.
        """
        for candidate in candidates:
            scores = candidate.get("scores", {})
            if not isinstance(scores, dict):
                scores = {}

            # Compute availability score from availability check results
            avail = candidate.get("availability", {})
            if isinstance(avail, dict):
                avail_score = self._compute_availability_score(avail)
                scores["availability"] = avail_score
            else:
                scores["availability"] = 50.0  # neutral if no data

            # Ensure all scores exist
            scores.setdefault("linguistic", 50.0)
            scores.setdefault("memorability", 50.0)
            scores.setdefault("strategy_alignment", 50.0)

            # Compute weighted overall score
            scores["overall"] = self._compute_overall(scores)
            candidate["scores"] = scores

        return candidates

    def _compute_availability_score(self, avail: dict[str, Any]) -> float:
        """Compute availability score from check results.

        Weights: domain_com (30), other domains (10 each),
        social (10 each), trademark (20).
        """
        score = 0.0
        max_score = 0.0

        # Domain .com (most valuable)
        if avail.get("domain_com") is not None:
            max_score += 30
            if avail["domain_com"]:
                score += 30

        # Other domains
        for key in ("domain_io", "domain_co"):
            if avail.get(key) is not None:
                max_score += 10
                if avail[key]:
                    score += 10

        # Social handles
        for key in ("twitter", "instagram", "linkedin"):
            if avail.get(key) is not None:
                max_score += 10
                if avail[key]:
                    score += 10

        # Trademark
        if avail.get("trademark_clear") is not None:
            max_score += 20
            if avail["trademark_clear"]:
                score += 20

        if max_score == 0:
            return 50.0  # No data → neutral

        return round((score / max_score) * 100, 1)

    def _compute_overall(self, scores: dict[str, float]) -> float:
        """Compute weighted overall score.

        Weights: strategy_alignment 30%, memorability 25%,
        linguistic 25%, availability 20%.
        """
        return round(
            scores.get("strategy_alignment", 0) * 0.30
            + scores.get("memorability", 0) * 0.25
            + scores.get("linguistic", 0) * 0.25
            + scores.get("availability", 0) * 0.20,
            1,
        )

    def summarize(
        self, candidates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Build scoring summary statistics."""
        if not candidates:
            return {"total": 0}

        scores = [
            c.get("scores", {}).get("overall", 0) for c in candidates
        ]
        return {
            "total": len(candidates),
            "avg_overall": round(sum(scores) / len(scores), 1),
            "max_overall": round(max(scores), 1),
            "min_overall": round(min(scores), 1),
            "avg_linguistic": round(
                sum(
                    c.get("scores", {}).get("linguistic", 0)
                    for c in candidates
                )
                / len(candidates),
                1,
            ),
            "avg_memorability": round(
                sum(
                    c.get("scores", {}).get("memorability", 0)
                    for c in candidates
                )
                / len(candidates),
                1,
            ),
            "avg_availability": round(
                sum(
                    c.get("scores", {}).get("availability", 0)
                    for c in candidates
                )
                / len(candidates),
                1,
            ),
            "avg_strategy_alignment": round(
                sum(
                    c.get("scores", {}).get("strategy_alignment", 0)
                    for c in candidates
                )
                / len(candidates),
                1,
            ),
        }
