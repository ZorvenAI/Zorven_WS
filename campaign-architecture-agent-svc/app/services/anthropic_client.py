"""Anthropic Claude Sonnet 4 wrapper for CAA service."""

import json
import logging
import re
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


def _repair_json(text: str) -> dict[str, Any] | None:
    """Attempt common JSON repairs on malformed text.

    Returns parsed dict/list on success, None if all repairs fail.
    """
    # Repair 1: Remove trailing commas before } or ]
    repaired = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(repaired, strict=False)
    except json.JSONDecodeError:
        pass

    # Repair 2: Fix missing commas between values
    # Pattern: "value" followed by whitespace then "key" (missing comma)
    repaired = re.sub(r'(")\s*\n\s*(")', r'\1,\n\2', repaired)
    # Also handle: } followed by whitespace then { or "
    repaired = re.sub(r"(})\s*\n\s*({)", r"\1,\n\2", repaired)
    repaired = re.sub(r'(})\s*\n\s*(")', r'\1,\n\2', repaired)
    # Handle: ] followed by whitespace then { or "
    repaired = re.sub(r"(])\s*\n\s*({)", r"\1,\n\2", repaired)
    try:
        return json.loads(repaired, strict=False)
    except json.JSONDecodeError:
        pass

    # Repair 3: Truncate at last valid closing brace if unterminated string
    # Find the last } that produces valid JSON when we slice up to it
    last_pos = len(repaired)
    for _ in range(5):  # Try up to 5 truncation attempts
        last_pos = repaired.rfind("}", 0, last_pos)
        if last_pos < 0:
            break
        candidate = repaired[: last_pos + 1]
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue

    return None


class AnthropicClient:
    """Wrapper around anthropic.AsyncAnthropic."""

    def __init__(self, client):
        self._client = client

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate a JSON response from Claude."""
        try:
            async with self._client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=max_tokens or settings.ANTHROPIC_MAX_TOKENS,
                thinking={"type": "disabled"},
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as _stream:
                response = await _stream.get_final_message()
            text = next(
                b.text for b in response.content if b.type == "text"
            )
            logger.debug(
                "Claude response: %d input, %d output tokens",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            # Step 1: Try strict parse on full text
            parsed = json.loads(text, strict=False)
            return _ensure_dict(parsed)
        except json.JSONDecodeError:
            logger.warning("Claude returned non-JSON, attempting extraction")
            text = next(
                b.text for b in response.content if b.type == "text"
            )
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0 or end <= start:
                logger.warning("No JSON object found in response")
                return {"raw_response": text}

            extracted = text[start:end]

            # Step 2: Try parsing the extracted block directly
            try:
                parsed = json.loads(extracted, strict=False)
                result = _ensure_dict(parsed)
                logger.info(
                    "Extracted JSON keys: %s (type=%s)",
                    list(result.keys())[:10],
                    type(parsed).__name__,
                )
                return result
            except json.JSONDecodeError:
                pass

            # Step 3: Attempt repairs on extracted text
            logger.warning(
                "Extracted JSON is malformed, attempting repair "
                "(%d chars)", len(extracted)
            )
            repaired = _repair_json(extracted)
            if repaired is not None:
                result = _ensure_dict(repaired)
                logger.info(
                    "Repaired JSON keys: %s (type=%s)",
                    list(result.keys())[:10],
                    type(repaired).__name__,
                )
                return result

            # Step 4: All repairs failed
            logger.warning(
                "All JSON repair attempts failed, returning raw response"
            )
            return {"raw_response": text}
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            raise
