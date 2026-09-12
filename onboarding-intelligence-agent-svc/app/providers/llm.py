"""Gemini text client, behind the §18.2 breaker.

Design §8.4, §18.2 · implemented by story C-02.

Scaffolded by A-05, whose docstring named A-06 as the implementer. A-06's
acceptance criteria cover the registry, guardrail chain, RBAC evaluator and
skill interfaces and never mention providers, so this stayed a stub. C-02 is
the first story that needs to generate anything.

**SDK choice.** ``google-genai``, the supported SDK, with the fleet default
model ``gemini-3.5-flash``.

This started on ``google-generativeai`` to match ``ai-brand-automator`` and
``content-agent-service``, argued on fleet consistency. That argument did not
survive contact with the package: from 0.8.6 it prints, at import, "All
support for the google.generativeai package has ended… please switch to the
google.genai package as soon as possible." Consistency with twenty-seven
services is worth something; inheriting an end-of-life dependency into a
brand-new service is worth less. OIA is the one place the switch costs
nothing, so it happens here first rather than never.

The other services still need migrating. That is a fleet-wide piece of work,
not something to do as a side effect of this story.
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
        #: The owning genai.Client. Held only to keep it alive — see
        #: _ensure_client. Never used directly.
        self._owner: Any = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def model_name(self) -> str:
        return self._model_name

    def _ensure_client(self) -> Any:
        """The ``aio.models`` handle, which is the whole surface we use.

        Narrowed deliberately: injecting the full ``genai.Client`` would make
        a test double reproduce two levels of nesting to stand in for one
        method call, and the extra structure would be scaffolding rather than
        anything the provider depends on.
        """
        if self._client is None:
            from google import genai

            # Keep the owning Client, do not discard it.
            #
            # `genai.Client(...).aio.models` on its own made the first
            # generation in a container succeed and every one after it fail
            # with "Cannot send a request, as the client has been closed".
            # Verified by A/B against the same workload and key: the image
            # without this line failed turns 2-4, the image with it passed
            # 4/4.
            #
            # The precise mechanism is not established — the Client has no
            # __del__, and the models handle does hold _api_client, so a
            # plain "it was garbage collected" story does not survive a local
            # probe. Holding the owner is the SDK's documented usage either
            # way, so this is the shape to keep regardless of which detail of
            # the SDK's lifetime management is responsible.
            #
            # Found by the C-03 e2e and only findable there: the unit tests
            # inject a stand-in, and the real-call test made exactly one
            # request. In production this broke every prep turn after the
            # first until the pod restarted.
            self._owner = genai.Client(api_key=self._api_key)
            self._client = self._owner.aio.models
        return self._client

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> str:
        """One completion.

        Temperature defaults low because every current caller is extracting or
        structuring facts, where invention is the failure mode. A caller that
        wants range should ask for it explicitly.

        ``model`` overrides the instance default for this call only. J-03 uses
        this to select gemini-2.0-flash for PROCESS extraction while the
        fleet default stays gemini-3.5-flash.
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

        effective_model = model or self._model_name
        try:
            response = await self._ensure_client().generate_content(
                model=effective_model,
                contents=prompt,
                config={"temperature": temperature},
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
