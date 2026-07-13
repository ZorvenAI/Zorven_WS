"""Resolve social posting action from user prompt.

Uses Gemini function-calling (primary) or keyword matching (fallback)
to determine whether the user wants to publish now or schedule for later.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from app.prompts.fallbacks import FALLBACK_ACTION_RESOLVER
from app.utils.prompt_sanitizer import sanitize_ai_prompt

if TYPE_CHECKING:
    from app.prompts.loader import AgentPromptClient

logger = logging.getLogger(__name__)

# Gemini tool declarations for function-calling
TOOL_DECLARATIONS = [
    {
        "name": "publish_now",
        "description": (
            "Publish social media posts immediately to platforms. "
            "Use this when the user wants to post right away, share now, "
            "or does not mention any scheduling or future time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Target platforms (e.g. linkedin, twitter)",
                },
            },
            "required": ["platforms"],
        },
    },
    {
        "name": "schedule_post",
        "description": (
            "Schedule social media posts for a future date/time. "
            "Use this when the user mentions scheduling, later, tomorrow, "
            "next week, a specific date/time, or wants it as a scheduled task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Target platforms (e.g. linkedin, twitter)",
                },
                "scheduled_date": {
                    "type": "string",
                    "description": (
                        "ISO 8601 datetime for when to publish. "
                        "If the user says 'tomorrow', use tomorrow at 09:00 UTC. "
                        "If the user says 'next week', use next Monday at 09:00 UTC. "
                        "If no specific time is given, default to tomorrow at 09:00 UTC."
                    ),
                },
            },
            "required": ["platforms", "scheduled_date"],
        },
    },
]

# Keywords that signal scheduling intent
SCHEDULE_KEYWORDS = [
    "schedule",
    "scheduled",
    "scheduling",
    "scheduled task",
    "schedule task",
    "schedule it",
    "schedule post",
    "later",
    "tomorrow",
    "next week",
    "next month",
    "next monday",
    "next tuesday",
    "next wednesday",
    "next thursday",
    "next friday",
    "timed",
    "calendar",
    "queue",
    "at a later time",
]


@dataclass
class ResolvedAction:
    """Result of action resolution."""

    action: str  # "publish_now" or "schedule"
    scheduled_date: str | None = None  # ISO 8601 datetime


class ActionResolver:
    """Determines posting action from user prompt."""

    def __init__(
        self,
        gemini_model: Any = None,
        prompt_loader: AgentPromptClient | None = None,
    ) -> None:
        self._model = gemini_model
        self._prompt_loader = prompt_loader

    async def resolve(self, prompt: str, platforms: list[str]) -> ResolvedAction:
        """Resolve the user's intended action from their prompt.

        Tries Gemini function-calling first, falls back to keyword matching.
        If Gemini returns publish_now but keywords clearly indicate scheduling,
        the keyword result takes precedence (Gemini sometimes misinterprets
        vague time references like "at an optimum date").
        """
        if self._model is not None:
            try:
                gemini_result = await self._gemini_resolve(prompt, platforms)
                # Cross-validate: if Gemini says publish_now but keywords
                # detect scheduling intent, trust the explicit keywords.
                if gemini_result.action == "publish_now":
                    keyword_result = self._keyword_resolve(prompt, platforms)
                    if keyword_result.action == "schedule":
                        logger.info(
                            "Keywords override Gemini: scheduling detected "
                            "in prompt despite Gemini returning publish_now"
                        )
                        return keyword_result
                return gemini_result
            except Exception as exc:
                logger.warning(
                    "Gemini action resolution failed, using keyword fallback: %s",
                    exc,
                )

        return self._keyword_resolve(prompt, platforms)

    async def _gemini_resolve(
        self, prompt: str, platforms: list[str]
    ) -> ResolvedAction:
        """Use Gemini function-calling to determine action."""
        import google.generativeai as genai

        tools = genai.protos.Tool(
            function_declarations=[
                genai.protos.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            k: genai.protos.Schema(
                                type=(
                                    genai.protos.Type.ARRAY
                                    if v.get("type") == "array"
                                    else genai.protos.Type.STRING
                                ),
                                description=v.get("description", ""),
                                **(
                                    {
                                        "items": genai.protos.Schema(
                                            type=genai.protos.Type.STRING
                                        )
                                    }
                                    if v.get("type") == "array"
                                    else {}
                                ),
                            )
                            for k, v in t["parameters"]["properties"].items()
                        },
                        required=t["parameters"].get("required", []),
                    ),
                )
                for t in TOOL_DECLARATIONS
            ]
        )

        if self._prompt_loader is not None:
            system_prompt = await self._prompt_loader.load(
                "zorven-social-action-resolver",
                fallback=FALLBACK_ACTION_RESOLVER,
            )
        else:
            system_prompt = FALLBACK_ACTION_RESOLVER

        sanitized_prompt = sanitize_ai_prompt(prompt)

        response = await asyncio.to_thread(
            self._model.generate_content,
            [system_prompt, sanitized_prompt],
            tools=[tools],
            generation_config={"temperature": 0.0},
            request_options={"timeout": 30},
        )

        # Extract function call from response
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    if fc.name == "schedule_post":
                        scheduled_date = dict(fc.args).get("scheduled_date")
                        scheduled_date = _normalize_date(scheduled_date, prompt)
                        return ResolvedAction(
                            action="schedule",
                            scheduled_date=scheduled_date,
                        )
                    return ResolvedAction(action="publish_now")

        # No function call returned — default to publish_now
        return ResolvedAction(action="publish_now")

    def _keyword_resolve(self, prompt: str, platforms: list[str]) -> ResolvedAction:
        """Keyword-based fallback for action resolution."""
        lower = prompt.lower()

        if any(kw in lower for kw in SCHEDULE_KEYWORDS):
            scheduled_date = _extract_date_from_prompt(lower)
            return ResolvedAction(
                action="schedule",
                scheduled_date=scheduled_date,
            )

        return ResolvedAction(action="publish_now")


def _default_scheduled_date() -> str:
    """Default scheduling time: tomorrow at 09:00 UTC."""
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()


def _normalize_date(raw: str | None, prompt: str) -> str:
    """Validate a date string is ISO 8601 and in the future.

    Gemini sometimes returns natural language like "tomorrow at 09:00 UTC"
    instead of a proper ISO 8601 datetime, or copies example dates from
    the tool description that are in the past.
    """
    if raw:
        try:
            parsed = datetime.fromisoformat(raw)
            # Ensure timezone-aware for comparison and output
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed > datetime.now(timezone.utc):
                return parsed.isoformat()
            logger.warning(
                "Gemini returned past date %r, falling back to prompt extraction",
                raw,
            )
        except (ValueError, TypeError):
            logger.warning(
                "Gemini returned non-ISO date %r, extracting from prompt", raw
            )
    return _extract_date_from_prompt(prompt.lower())


def _extract_date_from_prompt(prompt: str) -> str:
    """Extract a scheduling date from natural language.

    Returns ISO 8601 datetime string.
    """
    now = datetime.now(timezone.utc)

    if "tomorrow" in prompt:
        dt = now + timedelta(days=1)
        return dt.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()

    if "next week" in prompt or "next monday" in prompt:
        days_ahead = (7 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        dt = now + timedelta(days=days_ahead)
        return dt.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()

    if "next month" in prompt:
        if now.month == 12:
            dt = now.replace(year=now.year + 1, month=1, day=1)
        else:
            dt = now.replace(month=now.month + 1, day=1)
        return dt.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()

    # Try to extract "at HH:MM" or "at Ham/Hpm" patterns
    time_match = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", prompt)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = time_match.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        dt = now + timedelta(days=1)
        return dt.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()

    # Default: 24 hours from now
    return _default_scheduled_date()
