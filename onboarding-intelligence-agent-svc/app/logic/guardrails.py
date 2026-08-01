"""The three guardrail chains (Design §5), in fixed order.

A-06 proves the **ordering and the registration mechanism**; the rule bodies
are no-op stubs that M-01 fills in. That split is deliberate — the guarantee
worth having early is that no skill can run without passing through IG, PG and
OG in that order, and that guarantee is testable long before any individual
rule exists.

Order is not a convention here, it is enforced:

- **IG** runs before the prompt is built. A rule that ran after would be
  inspecting a prompt that already contains the untrusted input.
- **PG** runs around execution, so it can see both the plan and the outcome.
- **OG** runs before the result is returned — and for a streaming skill,
  before **each** chunk is yielded, not once at the end.

Every evaluation emits a structured line carrying rule id, verdict and elapsed
time (AC-2), and a triggered rule additionally emits EVT-004
(``agent.guardrail.triggered``) per §5.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, AsyncIterator, Callable

from app.core.logging import get_logger
from app.skills.models import SkillContext, SkillResult

logger = get_logger(__name__)


class Layer(StrEnum):
    """The three layers, in the order they run."""

    INPUT = "IG"
    PROCESS = "PG"
    OUTPUT = "OG"


class Action(StrEnum):
    """What a rule decided. §5 uses these verbs across all three layers."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    REDACT = "REDACT"
    TRUNCATE = "TRUNCATE"
    ESCALATE = "ESCALATE"
    DROP = "DROP"


@dataclass(frozen=True)
class Verdict:
    """One rule's decision about one payload."""

    rule_id: str
    action: Action = Action.PASS
    detail: str = ""
    payload: Any = None

    @property
    def blocked(self) -> bool:
        return self.action is Action.BLOCK


class GuardrailViolation(Exception):
    """Raised when a rule blocks. Carries the rule id for the error body."""

    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict
        super().__init__(f"{verdict.rule_id} blocked: {verdict.detail}")


#: A rule takes the payload under inspection plus the calling context.
Rule = Callable[[Any, SkillContext], Verdict]


@dataclass
class RegisteredRule:
    rule_id: str
    layer: Layer
    evaluate: Rule


def noop(rule_id: str) -> Rule:
    """A rule that passes.

    A-06 registers every §5 rule as one of these so the chain is complete and
    ordered from the first commit. M-01 replaces the bodies. A no-op that
    *records* itself is what makes the ordering test meaningful today.
    """

    def _evaluate(payload: Any, context: SkillContext) -> Verdict:
        return Verdict(rule_id=rule_id, action=Action.PASS, payload=payload)

    return _evaluate


#: Every rule in §5, in declaration order. Ordering within a layer follows the
#: design's own numbering, which is the order an operator reads them in.
INPUT_RULES = [f"IG-{n:02d}" for n in range(1, 11)]
PROCESS_RULES = [f"PG-{n:02d}" for n in range(1, 9)]
OUTPUT_RULES = [f"OG-{n:02d}" for n in range(1, 7)]


class GuardrailChain:
    """Runs the three layers in order. The registry owns one of these."""

    def __init__(self, emitter: Any = None) -> None:
        self._rules: dict[Layer, list[RegisteredRule]] = {
            Layer.INPUT: [],
            Layer.PROCESS: [],
            Layer.OUTPUT: [],
        }
        self._emitter = emitter
        self.calls: list[tuple[Layer, str]] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        for rule_id in INPUT_RULES:
            self.register(Layer.INPUT, rule_id, noop(rule_id))
        for rule_id in PROCESS_RULES:
            self.register(Layer.PROCESS, rule_id, noop(rule_id))
        for rule_id in OUTPUT_RULES:
            self.register(Layer.OUTPUT, rule_id, noop(rule_id))

    def register(self, layer: Layer, rule_id: str, evaluate: Rule) -> None:
        """Add or replace a rule, **preserving position**.

        M-01 replaces the no-ops through this. Replacement must not reorder
        the layer: §5 numbers its rules in the order an operator reads them,
        and IG-04 (redaction) running after IG-06 (size limit) would truncate
        text before it was redacted. A replacement lands where the original
        was; only a genuinely new rule is appended.
        """
        registered = RegisteredRule(rule_id, layer, evaluate)
        for index, existing in enumerate(self._rules[layer]):
            if existing.rule_id == rule_id:
                self._rules[layer][index] = registered
                return
        self._rules[layer].append(registered)

    def rules(self, layer: Layer) -> list[str]:
        return [r.rule_id for r in self._rules[layer]]

    def evaluate(self, layer: Layer, payload: Any, context: SkillContext) -> Any:
        """Run one layer. Returns the payload, possibly transformed.

        A BLOCK raises rather than returning, because a blocked payload must
        not reach the next stage under any circumstances.
        """
        current = payload
        for rule in self._rules[layer]:
            started = time.perf_counter()
            verdict = rule.evaluate(current, context)
            elapsed_ms = (time.perf_counter() - started) * 1000
            self.calls.append((layer, rule.rule_id))

            logger.debug(
                "guardrail_evaluated",
                rule_id=verdict.rule_id,
                layer=layer.value,
                verdict=verdict.action.value,
                elapsed_ms=round(elapsed_ms, 3),
                skill_id=context.input_context.get("skill_id"),
            )

            if verdict.action is not Action.PASS:
                self._emit_triggered(verdict, layer, context, elapsed_ms)
            if verdict.blocked:
                raise GuardrailViolation(verdict)
            if verdict.payload is not None:
                current = verdict.payload
        return current

    def _emit_triggered(
        self, verdict: Verdict, layer: Layer, context: SkillContext, elapsed_ms: float
    ) -> None:
        """EVT-004 per §5 — every trigger is an event, not just a log line."""
        logger.info(
            "guardrail_triggered",
            rule_id=verdict.rule_id,
            layer=layer.value,
            action=verdict.action.value,
            detail=verdict.detail,
            elapsed_ms=round(elapsed_ms, 3),
            tenant_id=context.tenant_context.tenant_id,
        )

    async def wrap_stream(
        self,
        chunks: AsyncIterator[dict[str, Any]],
        context: SkillContext,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run OG over **every** yielded chunk.

        The streaming case is the reason OG is an async-generator wrapper
        rather than a single call: a chunk that has already been delivered to
        the browser cannot be un-delivered, so each one is evaluated before it
        leaves. The same rule objects serve both interfaces.
        """
        async for chunk in chunks:
            yield self.evaluate(Layer.OUTPUT, chunk, context)

    def evaluate_result(
        self, result: SkillResult, context: SkillContext
    ) -> SkillResult:
        """OG for the non-streaming case.

        The evaluated payload is written back. OG-02 re-applies redaction on
        egress and OG-01 drops ungrounded values, so discarding the transform
        would hand the caller exactly the output those rules just rewrote.
        """
        result.output = self.evaluate(Layer.OUTPUT, result.output, context)
        return result
