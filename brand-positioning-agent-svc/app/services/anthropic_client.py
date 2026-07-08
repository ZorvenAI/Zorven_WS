"""Anthropic Claude Sonnet 4 wrapper for the Brand Positioning Agent.

Provides structured JSON responses from Claude for positioning analysis.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Wrapper around Anthropic's async client for BPA prompts."""

    def __init__(
        self,
        client: Any,
        model: str,
        max_tokens: int,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Send a prompt to Claude and parse the JSON response."""
        if not self._client:
            logger.warning("Anthropic client not initialized, returning empty")
            return {}

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            text = response.content[0].text
            # Try to extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from Claude response")
            return {"raw_text": response.content[0].text if response else ""}
        except Exception as exc:
            logger.error(
                "Anthropic API call failed (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return {}

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        """Send a prompt to Claude and return raw text response."""
        if not self._client:
            logger.warning("Anthropic client not initialized, returning empty")
            return ""

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except Exception as exc:
            logger.error(
                "Anthropic API call failed (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return ""
