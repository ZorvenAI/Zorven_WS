"""Variant diversity scorer for CGA (§5.2.1, AC-3).

Computes cosine similarity over variant headlines and primary texts
using character trigram frequency vectors. Higher diversity = higher score.
"""

import json
import logging
import math
from collections import Counter

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)


def _char_trigrams(text: str) -> Counter:
    """Build character trigram frequency vector."""
    text = text.lower().strip()
    if len(text) < 3:
        return Counter({text: 1}) if text else Counter()
    return Counter(text[i : i + 3] for i in range(len(text) - 2))


def _cosine_similarity(a: Counter, b: Counter) -> float:
    """Compute cosine similarity between two frequency vectors."""
    if not a or not b:
        return 0.0
    common_keys = set(a.keys()) & set(b.keys())
    dot = sum(a[k] * b[k] for k in common_keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _mean_pairwise_similarity(texts: list[str]) -> float:
    """Compute mean pairwise cosine similarity across texts."""
    if len(texts) < 2:
        return 1.0  # Single item = no diversity
    vectors = [_char_trigrams(t) for t in texts]
    total_sim = 0.0
    pair_count = 0
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            total_sim += _cosine_similarity(vectors[i], vectors[j])
            pair_count += 1
    return total_sim / pair_count if pair_count > 0 else 1.0


def _parse_cga_output(outputs) -> dict | None:
    """Parse CGA output from JSON string or dict."""
    if outputs is None:
        return None
    if isinstance(outputs, dict):
        return outputs
    try:
        parsed = json.loads(str(outputs))
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


@scorer(name="variant_diversity")
def variant_diversity(*, inputs, outputs, expectations=None):
    """Score creative variant diversity using cosine similarity.

    Extracts hook texts and copy texts, computes mean pairwise
    cosine similarity using character trigrams, and returns
    1.0 - similarity (higher diversity = higher score).

    Args:
        inputs: Model input (unused).
        outputs: CGA response JSON with hooks and copy_variants.
        expectations: Optional (unused).

    Returns:
        Feedback with value 0.0–1.0.
    """
    data = _parse_cga_output(outputs)
    if data is None:
        return Feedback(
            name="variant_diversity",
            value=0.0,
            rationale="Invalid or missing CGA output.",
        )

    texts = []
    hooks = data.get("hooks", [])
    if isinstance(hooks, list):
        for hook in hooks:
            if not isinstance(hook, dict):
                continue
            text = hook.get("hook_text", "").strip()
            if text:
                texts.append(text)
    copy_variants = data.get("copy_variants", [])
    if isinstance(copy_variants, list):
        for cv in copy_variants:
            if not isinstance(cv, dict):
                continue
            text = cv.get("copy_text", "").strip()
            if text:
                texts.append(text)

    if len(texts) < 2:
        return Feedback(
            name="variant_diversity",
            value=0.0,
            rationale=f"Need at least 2 text variants for diversity scoring, found {len(texts)}.",
        )

    mean_sim = _mean_pairwise_similarity(texts)
    score = round(max(0.0, min(1.0, 1.0 - mean_sim)), 4)

    return Feedback(
        name="variant_diversity",
        value=score,
        rationale=(
            f"Mean pairwise similarity: {mean_sim:.3f} across {len(texts)} variants. "
            f"Diversity score: {score:.3f}."
        ),
    )
