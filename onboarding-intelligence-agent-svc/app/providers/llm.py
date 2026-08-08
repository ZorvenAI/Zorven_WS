"""Gemini text client, behind the §18.2 breaker.

Design §8.4, §18.2 · implemented by story C-02.

Scaffolded by A-05, whose docstring named A-06 as the implementer. A-06's
acceptance criteria cover the registry, guardrail chain, RBAC evaluator and
skill interfaces and never mention providers, so this stayed a stub. C-02 is
the first story that needs to generate anything.

**SDK choice.** ``google-generativeai`` 0.8.x, matching
``ai-brand-automator`` and ``content-agent-service``, with the fleet default
model ``gemini-3.5-flash``. Google's newer ``google-genai`` package supersedes
it, but switching one service creates a second pattern in a fleet of
twenty-seven; that migration is worth doing deliberately and everywhere, not
as a side effect of this story.
"""

from __future__ import annotations

import logging
from typing import Any

from app.circuit_breaker.breaker import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerOpen,
)

logger = logging.getLogger(__name__)

DEPENDENCY = "llm"
DEFAULT_MODEL = "gemini-3.5-flash"


class LLMUnavailable(Exception):
    """Generation could not be performed. Carries the operator-facing reason."""

    def __init__(
        self, reason: str, *, degraded_mode: str = "MANUAL_CHECKBOXES"
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.degraded_mode = degraded_mode


class LLMProvider:
    """Generate text, or say plainly that it could not.

    Mirrors :class:`app.providers.tavily.TavilyProvider` deliberately — same
    breaker discipline, same "unavailable is not empty" distinction, same
    treatment of a missing key as degradation rather than a crash. Two
    providers that behave differently under failure would make the degraded
    paths hard to reason about together, and PREP uses both in one turn.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        breaker: CircuitBreaker | None = None,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model
        self._breaker = breaker or BreakerRegistry().get(DEPENDENCY)
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def model_name(self) -> str:
        return self._model_name

    def _ensure_client(self) -> Any:
        if self._client is None:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self._model_name)
        return self._client

    async def generate(self, prompt: str, *, temperature: float = 0.2) -> str:
        """One completion.

        Temperature defaults low because every current caller is extracting or
        structuring facts, where invention is the failure mode. A caller that
        wants range should ask for it explicitly.
        """
        if not self.configured:
            raise LLMUnavailable("no Gemini API key is configured")

        try:
            self._breaker.before_call()
        except CircuitBreakerOpen as exc:
            raise LLMUnavailable(
                exc.user_message or f"{exc.dependency} is unavailable",
                degraded_mode=exc.degraded_mode,
            ) from exc

        try:
            response = await self._ensure_client().generate_content_async(
                prompt,
                generation_config={"temperature": temperature},
            )
            text = self._text_of(response)
        except Exception as exc:
            # Broad by intent, for the reason evidenced in the Tavily provider's
            # tests: an SDK's raisable set is not enumerable from its signature,
            # and an unlisted exception escaping here breaks the chat turn.
            self._breaker.record_failure()
            logger.warning("gemini generation failed: %s: %s", type(exc).__name__, exc)
            raise LLMUnavailable(f"generation failed: {type(exc).__name__}") from exc

        self._breaker.record_success()
        return text

    @staticmethod
    def _text_of(response: Any) -> str:
        """Pull the text out, treating an empty completion as a failure.

        A safety block or a stop with no candidates returns a response object
        whose ``.text`` raises or is empty. Returning "" would let the caller
        build a brief out of nothing and present it as researched.
        """
        text = getattr(response, "text", None)
        if not text or not str(text).strip():
            raise ValueError("the model returned no text")
        return str(text)
