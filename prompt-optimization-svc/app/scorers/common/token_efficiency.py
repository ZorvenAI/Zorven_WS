"""Token efficiency scorer (§5.1).

Measures output conciseness relative to input length.
Uses character-based token approximation (~4 chars per token).
Penalizes excessively verbose outputs.
"""

import logging

from mlflow.entities.assessment import Feedback
from mlflow.genai.scorers import scorer

logger = logging.getLogger(__name__)

# Approximate characters per token for English text
CHARS_PER_TOKEN = 4

# Maximum acceptable output/input token ratio before penalty starts
MAX_RATIO = 10.0

# Minimum input token count for ratio calculation (avoids division
# by near-zero when input is very short)
MIN_INPUT_TOKENS_FOR_RATIO = 10


@scorer(name="token_efficiency")
def token_efficiency(*, inputs, outputs, expectations=None):
    """Score the token efficiency of the output.

    Outputs that are concise relative to input length score higher.
    Excessively verbose outputs (>10x input tokens) score lower.

    Args:
        inputs: Model input text.
        outputs: Model output text.
        expectations: Expected output (unused).

    Returns:
        Feedback with value 0.0–1.0 (1.0 = efficient).
    """
    if outputs is None or str(outputs).strip() == "":
        return Feedback(
            name="token_efficiency",
            value=1.0,
            rationale="Empty output — maximally efficient (no tokens used).",
        )

    output_text = str(outputs)
    input_text = str(inputs) if inputs else ""

    output_tokens = max(len(output_text) / CHARS_PER_TOKEN, 1)
    input_tokens = max(len(input_text) / CHARS_PER_TOKEN, MIN_INPUT_TOKENS_FOR_RATIO)

    ratio = output_tokens / input_tokens

    if ratio <= 1.0:
        score = 1.0
    elif ratio >= MAX_RATIO:
        score = 0.0
    else:
        # Linear decay from 1.0 to 0.0 as ratio goes from 1.0 to MAX_RATIO
        score = 1.0 - (ratio - 1.0) / (MAX_RATIO - 1.0)

    score = round(score, 4)

    return Feedback(
        name="token_efficiency",
        value=score,
        rationale=(
            f"Output ~{int(output_tokens)} tokens, input ~{int(input_tokens)} tokens "
            f"(ratio {ratio:.1f}x). Score: {score:.2f}."
        ),
    )
