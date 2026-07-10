"""Anthropic Claude Sonnet 4 wrapper for the Brand Architecture Agent.

Provides structured JSON responses from Claude for architecture analysis.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Wrapper around Anthropic's async client for BAA prompts."""

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
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                thinking={"type": "disabled"},
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as _stream:
                response = await _stream.get_final_message()

            raw_text = next(
                b.text for b in response.content if b.type == "text"
            )
            text = raw_text

            # Try to extract JSON from code fences
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            try:
                return json.loads(text, strict=False)
            except json.JSONDecodeError:
                # Try finding JSON object boundaries as fallback
                start = raw_text.find("{")
                end = raw_text.rfind("}")
                if start != -1 and end > start:
                    try:
                        return json.loads(raw_text[start : end + 1], strict=False)
                    except json.JSONDecodeError:
                        pass

                logger.error(
                    "Failed to parse JSON from Claude response "
                    "(length=%d, preview=%.200s)",
                    len(raw_text),
                    raw_text[:200],
                )
                return {
                    "raw_text": raw_text,
                    "findings": [
                        "Architecture analysis completed but response "
                        "format was unexpected. Please retry."
                    ],
                    "confidence_score": 0.0,
                }
        except Exception as exc:
            logger.error(
                "Anthropic API call failed (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return {
                "findings": [f"LLM API call failed: {str(exc)[:100]}"],
                "confidence_score": 0.0,
            }

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
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                thinking={"type": "disabled"},
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as _stream:
                response = await _stream.get_final_message()
            return next(
                b.text for b in response.content if b.type == "text"
            )
        except Exception as exc:
            logger.error(
                "Anthropic API call failed (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return ""
