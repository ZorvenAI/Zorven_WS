"""Hardcoded fallback prompts for the chat-titling-worker.

These prompts are used when the prompt-optimization-svc is unreachable
or when running in fallback-only mode.  They mirror the inline prompts
that existed before the prompt-loader integration.
"""

FALLBACK_TITLE_GENERATION = (
    "You are a session namer. Based on the following user message, "
    "generate a 3 to 5-word title for the chat session. "
    "Do not use punctuation. Do not use quotes. "
    "Example: 'Tesla Q4 Revenue Review'"
)

FALLBACK_MAP: dict[str, str] = {
    "zorven-titling-session": FALLBACK_TITLE_GENERATION,
}
