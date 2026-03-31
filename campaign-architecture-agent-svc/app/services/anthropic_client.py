"""Anthropic Claude Sonnet 4 wrapper for CAA service."""

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _ensure_dict(value: Any) -> dict[str, Any]:
    """Ensure parsed JSON is a dict, not a list or scalar."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, list):
        return {"items": value}
    return {"raw_response": value}


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
            parsed = json.loads(text)
            return _ensure_dict(parsed)
        except json.JSONDecodeError:
            logger.warning("Claude returned non-JSON, attempting extraction")
            text = response.content[0].text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end])
                return _ensure_dict(parsed)
            return {"raw_response": text}
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            raise
