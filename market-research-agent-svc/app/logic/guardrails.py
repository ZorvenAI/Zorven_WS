"""
3-layer guardrail architecture for market research agent.

InputGuardrail:  Validates and sanitizes incoming prompts.
OutputGuardrail: Validates outgoing research results.
"""

import logging
import re

from fastapi import HTTPException

from app.api.schemas import MarketResearchResponse

logger = logging.getLogger(__name__)

# PII detection patterns (basic)
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD_PATTERN = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

MAX_PROMPT_LENGTH = 5000


class InputGuardrail:
    """Validates and sanitizes incoming prompts."""

    def validate(self, prompt: str) -> str:
        """
        Validate and sanitize the input prompt.

        Returns the sanitized prompt or raises HTTPException(400).
        """
        if not prompt or not prompt.strip():
            raise HTTPException(status_code=400, detail="Input prompt cannot be empty")

        # Length check
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Input prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters",
            )

        # PII detection
        if _SSN_PATTERN.search(prompt):
            raise HTTPException(
                status_code=400,
                detail="Input contains potential SSN — please remove PII before submitting",
            )

        if _CREDIT_CARD_PATTERN.search(prompt):
            raise HTTPException(
                status_code=400,
                detail="Input contains potential credit card number — please remove PII",
            )

        # Sanitize: strip excessive whitespace
        sanitized = " ".join(prompt.split())
        return sanitized


class OutputGuardrail:
    """Validates outgoing research results."""

    def validate(self, response: MarketResearchResponse) -> MarketResearchResponse:
        """
        Validate and clean the output response.

        Returns the validated response.
        """
        # Clamp confidence score to [0, 1]
        if response.confidence_score < 0.0:
            response.confidence_score = 0.0
        elif response.confidence_score > 1.0:
            response.confidence_score = 1.0

        # Strip PII from findings
        response.findings = [self._strip_pii(f) for f in response.findings]
        response.recommendations = [
            self._strip_pii(r) for r in response.recommendations
        ]

        # Warn if no sources
        if not response.sources:
            logger.warning("Research response has no sources")

        return response

    @staticmethod
    def _strip_pii(text: str) -> str:
        """Remove potential PII from text."""
        text = _SSN_PATTERN.sub("[REDACTED-SSN]", text)
        text = _CREDIT_CARD_PATTERN.sub("[REDACTED-CC]", text)
        return text
