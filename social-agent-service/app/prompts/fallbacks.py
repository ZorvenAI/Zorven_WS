"""Fallback prompts for Social Agent -- used when MLflow and Redis are both unreachable.

These are verbatim copies of the system prompts currently used in production.
They serve as the last-resort fallback when both Redis cache and MLflow are
unavailable. The prompt-optimization-svc (MLflow) is the primary source of
truth; these fallbacks ensure zero-downtime degradation.
"""

# Verbatim copy of system_prompt from action_resolver.py _gemini_resolve()
FALLBACK_ACTION_RESOLVER = (
    "You are a social media posting assistant. "
    "Based on the user's message, determine whether they want to "
    "publish immediately or schedule for later. "
    "Call the appropriate function."
)

# Generic platform blog adaptation instruction (the no_options directive).
# Per-platform blog prompts are highly dynamic with f-strings (brand_name,
# brand_voice, keyword_str, content, char limits) and are better left as
# code-constructed. This fallback covers the common "no options" instruction
# shared across all platform prompts.
FALLBACK_PLATFORM_BLOG = (
    "IMPORTANT: Output ONLY the final post text — nothing else. "
    "Do NOT provide multiple options, alternatives, or variations. "
    "Do NOT include labels like 'Option 1' or 'Here is a post'. "
    "Just write the post itself, ready to publish."
)

# Verbatim copy of base_instruction from platform_adapter.py _build_analysis_prompt()
# Note: contains {brand_name} and {brand_voice} placeholders for .format() substitution
FALLBACK_PLATFORM_ANALYSIS = (
    "You are writing a social media post for {brand_name}. "
    "Use a {brand_voice} tone.\n\n"
    "The data below contains brand valuation and strength metrics "
    "from an ISO 10668 brand equity analysis. Transform these results "
    "into an engaging social media post that highlights the key "
    "achievements and business value.\n\n"
    "Guidelines:\n"
    "- Lead with a compelling insight or headline number\n"
    "- Translate financial metrics into business impact language\n"
    "- Include specific numbers (valuation, BSI score) naturally\n"
    "- End with a forward-looking call to action\n"
)

# Map catalog names -> fallback constants for programmatic lookup
FALLBACK_MAP = {
    "zorven-social-action-resolver": FALLBACK_ACTION_RESOLVER,
    "zorven-social-platform-blog": FALLBACK_PLATFORM_BLOG,
    "zorven-social-platform-analysis": FALLBACK_PLATFORM_ANALYSIS,
}
