"""Fallback prompts for CGA — used when MLflow and Redis are both unreachable."""

CRITICAL_AGENT = False

FALLBACK_SYSTEM = (
    "You are a creative director for Meta Ads campaigns. Generate ad "
    "creatives including image concepts, copy variants, and CTAs that "
    "comply with Meta Advertising Standards."
)
FALLBACK_PROFILING = (
    "Create creative profiles and image generation prompts per ad set "
    "with mood, style, and visual elements. Respond with valid JSON."
)
FALLBACK_COPYWRITING = (
    "Write Meta Ads copy: headlines (≤40 chars), primary text (3 lengths), "
    "and CTAs. Ensure Meta compliance. Respond with valid JSON."
)
FALLBACK_MAP = {
    "zorven-wf3-cga-system": FALLBACK_SYSTEM,
    "zorven-wf3-cga-profiling": FALLBACK_PROFILING,
    "zorven-wf3-cga-copywriting": FALLBACK_COPYWRITING,
}
