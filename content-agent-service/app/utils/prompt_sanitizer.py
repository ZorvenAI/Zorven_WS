"""Sanitize user prompts before passing to LLMs.

Strips prompt-injection patterns and control characters to reduce
the risk of overriding system instructions.
"""

import logging
import re

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(previous|above|prior)\s+instructions?",
        r"disregard\s+(previous|above|prior)\s+instructions?",
        r"system\s*:",
        r"admin\s*:",
        r"root\s*:",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"\[SYSTEM\]",
        r"\[ADMIN\]",
        r"forget\s+everything",
        r"new\s+instructions?",
        r"reveal\s+(your|the)\s+(prompt|instructions|system)",
    ]
]

MAX_PROMPT_LENGTH = 5000


def sanitize_ai_prompt(prompt: str) -> str:
    """Sanitize an AI prompt to mitigate prompt-injection attacks.

    Removes patterns that attempt to override system instructions,
    strips control characters, and enforces a max length.
    """
    if not isinstance(prompt, str):
        prompt = str(prompt)

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(prompt):
            logger.warning(
                "Potential prompt injection detected: %s", pattern.pattern
            )
            prompt = pattern.sub("", prompt)

    if len(prompt) > MAX_PROMPT_LENGTH:
        logger.info(
            "Prompt truncated from %d to %d characters",
            len(prompt),
            MAX_PROMPT_LENGTH,
        )
        prompt = prompt[:MAX_PROMPT_LENGTH]

    # Remove control characters (keep newline, carriage return, tab)
    prompt = "".join(ch for ch in prompt if ord(ch) >= 32 or ch in "\n\r\t")

    return prompt.strip()
