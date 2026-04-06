"""Thin wrapper around the Anthropic async client.

Used for Claude Sonnet 4 analysis narrative generation.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Wrapper providing structured LLM calls for optimization analysis."""

    def __init__(self, client, model: str = "claude-sonnet-4-20250514"):
        self._client = client
        self.model = model

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """Send a prompt and return the text response."""
        if self._client is None:
            return ""
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except Exception as exc:
            logger.error("Anthropic generate failed: %s", exc)
            return ""

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Send a prompt and parse the response as JSON."""
        text = await self.generate(
            system_prompt, user_prompt, max_tokens, temperature
        )
        if not text:
            return {}
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except (json.JSONDecodeError, IndexError) as exc:
            logger.warning("Failed to parse LLM JSON response: %s", exc)
            return {"raw_text": text, "parse_error": str(exc)}
