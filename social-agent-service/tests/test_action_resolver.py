"""Tests for the ActionResolver — Gemini + keyword fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.logic.action_resolver import (
    ActionResolver,
    ResolvedAction,
    _default_scheduled_date,
    _extract_date_from_prompt,
)


class TestKeywordFallback:
    """Keyword-based resolution (no Gemini model)."""

    async def test_schedule_keyword_detected(self):
        resolver = ActionResolver(gemini_model=None)
        result = await resolver.resolve(
            "Write a blog about Tesla and schedule it on LinkedIn",
            ["linkedin"],
        )
        assert result.action == "schedule"
        assert result.scheduled_date is not None

    async def test_schedule_tomorrow_detected(self):
        resolver = ActionResolver(gemini_model=None)
        result = await resolver.resolve(
            "Post this to LinkedIn tomorrow",
            ["linkedin"],
        )
        assert result.action == "schedule"
        assert result.scheduled_date is not None

    async def test_schedule_next_week_detected(self):
        resolver = ActionResolver(gemini_model=None)
        result = await resolver.resolve(
            "Schedule this post for next week on Twitter",
            ["twitter"],
        )
        assert result.action == "schedule"

    async def test_scheduled_task_keyword(self):
        resolver = ActionResolver(gemini_model=None)
        result = await resolver.resolve(
            "Post it as a scheduled task on LinkedIn",
            ["linkedin"],
        )
        assert result.action == "schedule"

    async def test_publish_now_no_schedule_keywords(self):
        resolver = ActionResolver(gemini_model=None)
        result = await resolver.resolve(
            "Write a blog about Tesla and post it on LinkedIn",
            ["linkedin"],
        )
        assert result.action == "publish_now"
        assert result.scheduled_date is None

    async def test_publish_now_generic_prompt(self):
        resolver = ActionResolver(gemini_model=None)
        result = await resolver.resolve(
            "Promote our latest blog",
            ["linkedin", "twitter"],
        )
        assert result.action == "publish_now"


class TestGeminiResolve:
    """Gemini function-calling resolution."""

    async def test_gemini_returns_schedule(self):
        mock_model = MagicMock()
        # Build a mock response with a function call
        fc = MagicMock()
        fc.name = "schedule_post"
        fc.args = {"platforms": ["linkedin"], "scheduled_date": "2026-03-01T09:00:00+00:00"}

        part = MagicMock()
        part.function_call = fc

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response = MagicMock()
        response.candidates = [candidate]

        mock_model.generate_content = MagicMock(return_value=response)

        resolver = ActionResolver(gemini_model=mock_model)
        result = await resolver.resolve(
            "Schedule a post about Tesla on LinkedIn for tomorrow",
            ["linkedin"],
        )
        assert result.action == "schedule"
        assert result.scheduled_date == "2026-03-01T09:00:00+00:00"

    async def test_gemini_returns_publish_now(self):
        mock_model = MagicMock()

        fc = MagicMock()
        fc.name = "publish_now"
        fc.args = {"platforms": ["linkedin"]}

        part = MagicMock()
        part.function_call = fc

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response = MagicMock()
        response.candidates = [candidate]

        mock_model.generate_content = MagicMock(return_value=response)

        resolver = ActionResolver(gemini_model=mock_model)
        result = await resolver.resolve(
            "Post a blog about Tesla on LinkedIn now",
            ["linkedin"],
        )
        assert result.action == "publish_now"
        assert result.scheduled_date is None

    async def test_gemini_error_falls_back_to_keywords(self):
        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(
            side_effect=Exception("Gemini API error")
        )

        resolver = ActionResolver(gemini_model=mock_model)
        result = await resolver.resolve(
            "Schedule this post on LinkedIn for tomorrow",
            ["linkedin"],
        )
        # Should fall back to keyword detection
        assert result.action == "schedule"

    async def test_gemini_no_function_call_defaults_publish_now(self):
        mock_model = MagicMock()

        # Response with text, no function call
        part = MagicMock()
        part.function_call = None
        del part.function_call  # hasattr returns False

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response = MagicMock()
        response.candidates = [candidate]

        mock_model.generate_content = MagicMock(return_value=response)

        resolver = ActionResolver(gemini_model=mock_model)
        result = await resolver.resolve(
            "Write something about Tesla",
            ["linkedin"],
        )
        assert result.action == "publish_now"


class TestDateExtraction:
    """Date extraction from natural language prompts."""

    def test_tomorrow(self):
        result = _extract_date_from_prompt("post this tomorrow")
        dt = datetime.fromisoformat(result)
        assert dt.hour == 9
        assert dt.minute == 0

    def test_next_week(self):
        result = _extract_date_from_prompt("schedule for next week")
        dt = datetime.fromisoformat(result)
        assert dt.hour == 9
        # Should be a Monday
        assert dt.weekday() == 0

    def test_next_month(self):
        result = _extract_date_from_prompt("post this next month")
        dt = datetime.fromisoformat(result)
        assert dt.day == 1
        assert dt.hour == 9

    def test_at_time_pm(self):
        result = _extract_date_from_prompt("schedule at 3pm")
        dt = datetime.fromisoformat(result)
        assert dt.hour == 15
        assert dt.minute == 0

    def test_at_time_with_minutes(self):
        result = _extract_date_from_prompt("schedule at 10:30 am")
        dt = datetime.fromisoformat(result)
        assert dt.hour == 10
        assert dt.minute == 30

    def test_default_date_24h(self):
        """No date keyword → defaults to tomorrow 09:00 UTC."""
        result = _extract_date_from_prompt("schedule this later")
        dt = datetime.fromisoformat(result)
        assert dt.hour == 9


class TestGeminiKeywordCrossValidation:
    """When Gemini says publish_now but keywords say schedule, keywords win."""

    async def test_keywords_override_gemini_publish_now(self):
        """If prompt says 'schedule' but Gemini returns publish_now, use keywords."""
        mock_model = MagicMock()

        fc = MagicMock()
        fc.name = "publish_now"
        fc.args = {"platforms": ["twitter", "facebook"]}

        part = MagicMock()
        part.function_call = fc

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response = MagicMock()
        response.candidates = [candidate]

        mock_model.generate_content = MagicMock(return_value=response)

        resolver = ActionResolver(gemini_model=mock_model)
        result = await resolver.resolve(
            "Write a blog on Apple and schedule to post it on Twitter and Facebook at an optimum date",
            ["twitter", "facebook"],
        )
        # Keywords detect "schedule" and override Gemini's publish_now
        assert result.action == "schedule"
        assert result.scheduled_date is not None

    async def test_gemini_publish_now_without_schedule_keywords_stays(self):
        """If prompt has no schedule keywords, trust Gemini's publish_now."""
        mock_model = MagicMock()

        fc = MagicMock()
        fc.name = "publish_now"
        fc.args = {"platforms": ["linkedin"]}

        part = MagicMock()
        part.function_call = fc

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response = MagicMock()
        response.candidates = [candidate]

        mock_model.generate_content = MagicMock(return_value=response)

        resolver = ActionResolver(gemini_model=mock_model)
        result = await resolver.resolve(
            "Post a blog about Tesla on LinkedIn right now",
            ["linkedin"],
        )
        # No schedule keywords → Gemini's publish_now is correct
        assert result.action == "publish_now"
        assert result.scheduled_date is None


class TestDefaultScheduledDate:
    def test_returns_tomorrow_9am(self):
        result = _default_scheduled_date()
        dt = datetime.fromisoformat(result)
        now = datetime.now(timezone.utc)
        # Should be roughly 24h from now
        assert dt.hour == 9
        assert dt.minute == 0
        assert dt.day != now.day or dt.month != now.month
