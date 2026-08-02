"""Model factories for the OIA session models (AC-4).

Every later story in Epic B and beyond builds its fixtures from these, so the
defaults are deliberately valid and terminal-free: a factory that produced a
COMPLETED session by default would let a caller create two of them for one
company without tripping the constraint the tests exist to prove.

Plain callables rather than factory_boy — the repository has no factory_boy
dependency, and these need no more than sensible defaults.
"""

from __future__ import annotations

from typing import Any

from onboarding.models import Company

from apps.onboarding.models import (
    OnboardingSession,
    Question,
    Questionnaire,
    QuestionnaireStatus,
    QuestionOrigin,
    QuestionStatus,
    SessionStatus,
    WorkflowTarget,
)


def make_company(tenant=None, **kwargs: Any) -> Company:
    defaults = {"name": "Acme Coffee Roasters", "industry": "Food & Beverage"}
    defaults.update(kwargs)
    if tenant is not None:
        defaults["tenant"] = tenant
    return Company.objects.create(**defaults)


def make_session(
    company: Company | None = None,
    tenant=None,
    status: str = SessionStatus.DRAFT,
    **kwargs: Any,
) -> OnboardingSession:
    """A non-terminal session by default, so the uniqueness rule applies.

    When a tenanted company is passed without an explicit tenant, the session
    inherits the company's. Otherwise the fixture would be tenant-less and so
    visible to *every* tenant under the backward-compatibility rule in
    ``tenant_scope_q`` — which would quietly weaken any later test that means
    to prove scoping.
    """
    if company is None:
        company = make_company(tenant=tenant)
    elif tenant is None:
        tenant = getattr(company, "tenant", None)
    defaults = {
        "company": company,
        "tenant": tenant,
        "status": status,
        "prompt_versions": {},
        "evidence_manifest_hash": "",
    }
    defaults.update(kwargs)
    return OnboardingSession.objects.create(**defaults)


def make_questionnaire(
    company: Company | None = None,
    session: OnboardingSession | None = None,
    tenant=None,
    status: str = QuestionnaireStatus.DRAFT,
    **kwargs: Any,
) -> Questionnaire:
    if company is None:
        company = session.company if session else make_company(tenant=tenant)
    if tenant is None:
        # Same reasoning as make_session: inherit rather than silently
        # producing a globally-visible fixture.
        tenant = getattr(session, "tenant", None) or getattr(company, "tenant", None)
    defaults = {
        "company": company,
        "session": session,
        "tenant": tenant,
        "status": status,
        "depth": 3,
        "question_count": 0,
        "version": 1,
    }
    defaults.update(kwargs)
    return Questionnaire.objects.create(**defaults)


def make_question(
    questionnaire: Questionnaire | None = None,
    order: int = 1,
    text: str = "How did the business start?",
    **kwargs: Any,
) -> Question:
    """A question with no score and no evidence — the only valid empty state.

    Callers wanting a scored question must supply both fields; that is the
    OG-06 rule, and the factory does not offer a way around it.
    """
    if questionnaire is None:
        questionnaire = make_questionnaire()
    defaults = {
        "questionnaire": questionnaire,
        "order": order,
        "text": text,
        "origin": QuestionOrigin.PREPARED,
        "workflow_target": WorkflowTarget.WF1,
        "status": QuestionStatus.OPEN,
    }
    defaults.update(kwargs)
    return Question.objects.create(**defaults)


def evidence_span(
    recording_id: str = "r_01", t_start: float = 812.4, t_end: float = 815.9
) -> dict[str, Any]:
    """One evidence span in the §10.1 shape."""
    return {"recording_id": recording_id, "t_start": t_start, "t_end": t_end}
