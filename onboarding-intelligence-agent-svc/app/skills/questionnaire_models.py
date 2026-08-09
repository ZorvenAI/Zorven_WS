"""SKL-OIA-02's output shape.

Design §8.1 · story C-03.

Mirrors the Django ``Question``/``Questionnaire`` field names rather than
inventing agent-side ones, because the generated set is posted straight to
``/api/v1/onboarding/questionnaires/generate/``. A translation layer between
two shapes that mean the same thing is a place for them to disagree.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: §10.1's three workflows. WF3 is the one the requirement review added and
#: the one a model silently drops — FR-PREP-08 makes its absence a generation
#: failure, not a warning.
WORKFLOWS = ("WF1", "WF2", "WF3")


class GeneratedQuestion(BaseModel):
    """One question, in the shape Django stores."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    workflow_target: str
    #: Empty means "this question does not map to a Company field", which is
    #: legitimate — AC-2 says "where applicable". It is not a missing value.
    target_field: str = ""

    @field_validator("workflow_target")
    @classmethod
    def _known_workflow(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in WORKFLOWS:
            raise ValueError(f"workflow_target must be one of {WORKFLOWS}")
        return upper


class GeneratedQuestionnaire(BaseModel):
    """What SKL-OIA-02 returns."""

    model_config = ConfigDict(extra="forbid")

    questions: list[GeneratedQuestion] = Field(default_factory=list)
    depth: str = "standard"
    requested_count: int = 0

    #: AC-3. Reported with the set rather than fetched separately, because the
    #: operator's next move — "give me more WF3" — depends on seeing it in the
    #: same turn they see the questions.
    coverage: dict[str, float] = Field(default_factory=dict)
    thin_workflows: list[str] = Field(default_factory=list)

    degraded: bool = False
    degraded_reason: str = ""

    @property
    def count(self) -> int:
        return len(self.questions)

    def recompute_coverage(self) -> None:
        """Set ``coverage`` and ``thin_workflows`` from the current questions.

        Called after the count is enforced, never before: trimming or topping
        up changes the mix, and coverage computed on the pre-trim set would
        describe a questionnaire the operator never sees.
        """
        total = len(self.questions)
        if not total:
            self.coverage = {w: 0.0 for w in WORKFLOWS}
            self.thin_workflows = list(WORKFLOWS)
            return

        counts = Counter(q.workflow_target for q in self.questions)
        self.coverage = {w: counts.get(w, 0) / total for w in WORKFLOWS}
        self.thin_workflows = [w for w in WORKFLOWS if counts.get(w, 0) == 0]

    def summary_line(self) -> str:
        """One line for the chat turn (AC-3).

        Names what is thin rather than only what is covered: the operator's
        action — "ask for more before approving" — depends on knowing the gap,
        and a list of percentages makes them work it out.
        """
        if self.degraded:
            return (
                f"Could not generate a questionnaire ({self.degraded_reason}). "
                "Nothing was saved."
            )
        parts = ", ".join(f"{w} {self.coverage.get(w, 0.0):.0%}" for w in WORKFLOWS)
        line = f"{self.count} questions at {self.depth} depth — coverage {parts}."
        if self.thin_workflows:
            line += (
                f" Nothing yet for {', '.join(self.thin_workflows)} — "
                "ask for more before approving."
            )
        return line
