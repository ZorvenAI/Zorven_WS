"""Prompt injection mitigation for LLM calls."""

import logging
import re

logger = logging.getLogger(__name__)

MAX_PROMPT_LENGTH = 5000

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"(?:system|admin|root)\s*:", re.IGNORECASE),
    re.compile(r"<\|im_(?:start|end)\|>", re.IGNORECASE),
    re.compile(r"\[(?:SYSTEM|ADMIN)\]", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"new\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+your\s+prompt", re.IGNORECASE),
]


def sanitize_ai_prompt(prompt: str) -> str:
    """Remove potential prompt-injection patterns and truncate."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(prompt):
            logger.warning(
                "Potential prompt injection detected: %s", pattern.pattern
            )
            prompt = pattern.sub("", prompt)

    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt = prompt[:MAX_PROMPT_LENGTH]

    prompt = "".join(ch for ch in prompt if ord(ch) >= 32 or ch in "\n\r\t")
    return prompt.strip()
