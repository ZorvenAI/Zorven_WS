"""Anthropic Claude Sonnet 4 wrapper for BSA service."""

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Wrapper around anthropic.AsyncAnthropic."""

    def __init__(self, client):
        self._client = client

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Generate a JSON response from Claude."""
        try:
            response = await self._client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=max_tokens or settings.ANTHROPIC_MAX_TOKENS,
                temperature=temperature or settings.ANTHROPIC_TEMPERATURE,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text
            logger.debug(
                "Claude response: %d input, %d output tokens",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error("Claude returned non-JSON, attempting extraction")
            text = response.content[0].text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            return {"raw_response": text}
        except Exception as exc:
            logger.error(
                "Claude API error (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            raise
