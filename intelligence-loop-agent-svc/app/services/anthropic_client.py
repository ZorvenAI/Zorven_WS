"""Anthropic Claude client wrapper for ILA learning extraction.

Fail-open: if no API key is configured, ``extract_learnings`` returns a
deterministic mock report so unit tests and offline dev still work.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore


class AnthropicClient:
    """Async wrapper around Anthropic Claude (Sonnet 4)."""

    def __init__(
        self,
        api_key: str | None,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.2,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._client: Any = None
        if api_key and anthropic is not None:
            try:
                self._client = anthropic.AsyncAnthropic(api_key=api_key)
                logger.info("Anthropic client initialized (model=%s)", model)
            except Exception as exc:
                logger.warning("Anthropic init failed (fail-open): %s", exc)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """Call Claude and return parsed JSON.

        Returns ``{}`` on failure (caller decides whether to fall back).
        """
        if not self._client:
            return {}
        try:
            msg = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(
                block.text for block in msg.content if getattr(block, "text", None)
            )
            return _safe_json_loads(text)
        except Exception as exc:
            logger.warning("Anthropic call failed (fail-open): %s", exc)
            return {}


def _safe_json_loads(text: str) -> dict[str, Any]:
    """Tolerant JSON parser — strips markdown fences and trailing prose."""
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Last resort: extract first {...} block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass
    logger.warning("Could not parse Anthropic JSON response")
    return {}
