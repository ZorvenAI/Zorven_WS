"""Anthropic Claude Sonnet 4 wrapper for CGA service."""

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

# Matches a trailing comma before ] or } (valid in JS/Python, invalid in JSON).
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _repair_json(text: str) -> str:
    """Apply common tolerant-repair transforms to a JSON-ish string.

    Currently strips trailing commas before ``}`` / ``]`` which Claude
    occasionally emits. Kept conservative — string-aware so we don't
    touch commas inside string literals.
    """
    out: list[str] = []
    in_str = False
    esc = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            # Peek ahead for whitespace then } or ]
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                # Skip the comma
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _ensure_dict(value: Any) -> dict[str, Any]:
    """Ensure parsed JSON is a dict, not a list or scalar."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, list):
        return {"items": value}
    return {"raw_response": value}


def _strip_fences(text: str) -> str:
    """Extract content from a ```json ... ``` code fence if present."""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _find_balanced_json(text: str) -> str | None:
    """Find the first balanced JSON object in text via brace scanning.

    Handles strings (with escapes) so braces inside string literals don't
    confuse the depth counter. Returns the substring or None.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
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
            stop_reason = getattr(response, "stop_reason", None)
            logger.debug(
                "Claude response: %d input, %d output tokens, stop_reason=%s",
                response.usage.input_tokens,
                response.usage.output_tokens,
                stop_reason,
            )
            if stop_reason == "max_tokens":
                logger.warning(
                    "Claude response hit max_tokens (%d) — JSON likely "
                    "truncated. Consider raising max_tokens for this call.",
                    max_tokens or settings.ANTHROPIC_MAX_TOKENS,
                )
            try:
                return _ensure_dict(json.loads(text))
            except json.JSONDecodeError:
                pass

            # Fallback: strip markdown fences and do a brace-balanced scan
            logger.warning(
                "Claude returned non-JSON (stop_reason=%s), attempting extraction",
                stop_reason,
            )
            candidate = _strip_fences(text)
            try:
                return _ensure_dict(json.loads(candidate))
            except json.JSONDecodeError:
                pass

            balanced = _find_balanced_json(candidate)
            if balanced:
                for attempt_label, attempt_text in (
                    ("balanced", balanced),
                    ("balanced+repair", _repair_json(balanced)),
                ):
                    try:
                        parsed = json.loads(attempt_text)
                        result = _ensure_dict(parsed)
                        logger.info(
                            "Extracted JSON via %s: keys=%s (type=%s)",
                            attempt_label,
                            list(result.keys())[:10],
                            type(parsed).__name__,
                        )
                        return result
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.warning(
                            "%s parse failed at pos=%s msg=%s",
                            attempt_label,
                            getattr(exc, "pos", "?"),
                            str(exc)[:200],
                        )
            # Last-ditch: repair the whole candidate
            try:
                parsed = json.loads(_repair_json(candidate))
                result = _ensure_dict(parsed)
                logger.info(
                    "Extracted JSON via full-repair: keys=%s",
                    list(result.keys())[:10],
                )
                return result
            except (json.JSONDecodeError, ValueError):
                pass

            logger.warning(
                "JSON extraction failed (text_len=%d, stop_reason=%s). "
                "Head=%r Tail=%r",
                len(text),
                stop_reason,
                text[:400],
                text[-400:],
            )
            return {"raw_response": text}
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            raise
