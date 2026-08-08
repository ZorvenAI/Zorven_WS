"""OG-01 — every asserted value must be grounded in a source.

Design §5 OG-01, §18.4 ERR-11 · story C-02.

This is a **real rule body registered into the chain**, not grounding logic
hidden inside the skill. Three reasons:

1. C-02's own test case says so — ``test_og_unsourced_fact_moves_to_unknowns``
   lives in ``tests/test_guardrails.py`` and proves "OG grounding applies to
   research too".
2. A-06 built ``GuardrailChain.register`` precisely so a rule body can replace
   a no-op without reordering the layer. Using it is what that mechanism is
   for.
3. M-01 completes the guardrail suite later. It should find a working OG-01 to
   extend, not a no-op plus a private copy of the same logic in one skill —
   the second of which it would have no reason to look for.

**What it does not do.** It does not verify that a source *supports* its
claim; that is a factuality question §17.4 evaluates offline against
``oia.research_brief``. OG-01 asks only whether a claim is attributed at all,
which is checkable here and now.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.logic.guardrails import Action, Verdict
from app.skills.models import SkillContext

logger = get_logger(__name__)

RULE_ID = "OG-01"

#: Keys whose list values are subject to grounding. Scoped rather than
#: universal: OG-01 governs asserted *facts*, and applying it to every list in
#: every skill's output would strip legitimately unsourced material — the
#: open_unknowns list being the obvious one, since an unknown is by definition
#: not sourced.
GROUNDED_LIST_KEYS = ("facts",)

UNKNOWNS_KEY = "open_unknowns"


def _is_sourced(item: Any) -> bool:
    if not isinstance(item, dict):
        # A fact that is not a mapping cannot carry a source, so it cannot be
        # grounded. Dropping it to unknowns is the safe reading.
        return False
    url = item.get("source_url")
    return isinstance(url, str) and url.strip().startswith(("http://", "https://"))


def _describe(item: Any) -> str:
    """Turn a dropped fact into an unknown an operator can act on."""
    if isinstance(item, dict):
        statement = str(item.get("statement") or "").strip()
        if statement:
            return f"Unverified: {statement}"
    return "Unverified claim dropped for lack of a source"


def ground_output(payload: Any, context: SkillContext) -> Verdict:
    """Move every unsourced fact into ``open_unknowns``.

    Returns DROP when anything moved, PASS otherwise. The transformed payload
    is carried on the verdict because ``evaluate_result`` assigns it back —
    "a transform the skill never sees is not a guardrail".

    Demotion rather than deletion is the whole design. A claim the agent could
    not source is not worthless: it is a thing worth *asking about*, and
    SKL-OIA-02 turns unknowns straight into questions. Deleting it would throw
    away the signal that the agent went looking and came back empty.
    """
    if not isinstance(payload, dict):
        return Verdict(rule_id=RULE_ID, action=Action.PASS, payload=payload)

    moved: list[str] = []
    result = dict(payload)

    for key in GROUNDED_LIST_KEYS:
        items = result.get(key)
        if not isinstance(items, list):
            continue

        kept = [item for item in items if _is_sourced(item)]
        if len(kept) != len(items):
            moved.extend(_describe(item) for item in items if not _is_sourced(item))
            result[key] = kept

    if not moved:
        return Verdict(rule_id=RULE_ID, action=Action.PASS, payload=payload)

    unknowns = result.get(UNKNOWNS_KEY)
    result[UNKNOWNS_KEY] = (
        list(unknowns) if isinstance(unknowns, list) else []
    ) + moved

    logger.warning(
        "og_01_dropped_ungrounded",
        rule_id=RULE_ID,
        dropped=len(moved),
        tenant_id=context.tenant_context.tenant_id,
        skill_hint=context.input_context.get("skill_id", ""),
    )

    return Verdict(
        rule_id=RULE_ID,
        action=Action.DROP,
        detail=f"{len(moved)} unsourced value(s) moved to {UNKNOWNS_KEY}",
        payload=result,
    )
