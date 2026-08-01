"""AC-4 — the admin is operable, and scoped (PR #537 review).

The admin is a direct path to the ORM. Three findings from review are covered
here: the scoping predicate must match the manager's, Question must be scoped
through its parent, and neither may leak across tenants.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from apps.onboarding.admin import (
    OnboardingSessionAdmin,
    QuestionAdmin,
    QuestionnaireAdmin,
)
from apps.onboarding.models import OnboardingSession, Question, Questionnaire
from apps.onboarding.tests.factories import (
    make_company,
    make_question,
    make_questionnaire,
    make_session,
)

pytestmark = pytest.mark.django_db


class FakeRequest:
    """Minimal request: the admin reads only .user and .tenant."""

    def __init__(self, user, tenant=None):
        self.user = user
        self.tenant = tenant


@pytest.fixture
def other_tenant(db):
    from tenants.models import Tenant

    return Tenant.objects.create(name="Other", schema_name="other_admin_tenant")


def queryset_for(admin_class, model, user, tenant):
    return admin_class(model, AdminSite()).get_queryset(FakeRequest(user, tenant))


def test_all_three_models_are_registered():
    from django.contrib import admin as django_admin

    for model in (OnboardingSession, Questionnaire, Question):
        assert model in django_admin.site._registry, model


def test_session_admin_hides_other_tenants(user, public_tenant, other_tenant):
    mine = make_session(tenant=public_tenant)
    theirs = make_session(tenant=other_tenant)

    visible = queryset_for(
        OnboardingSessionAdmin, OnboardingSession, user, public_tenant
    )
    assert mine in visible
    assert theirs not in visible


def test_session_admin_keeps_pre_tenant_rows_visible(user, public_tenant):
    """Review finding: the admin dropped the tenant__isnull half.

    Its own docstring promised those rows stayed visible, and the manager's
    for_tenant() includes them, so the two disagreed about what a tenant
    could see.
    """
    legacy = make_session(company=make_company(), tenant=None)

    visible = queryset_for(
        OnboardingSessionAdmin, OnboardingSession, user, public_tenant
    )
    assert legacy in visible


def test_admin_and_manager_agree(user, public_tenant, other_tenant):
    """The predicate is defined once; this proves the two callers match."""
    make_session(tenant=public_tenant)
    make_session(company=make_company(), tenant=None)
    make_session(tenant=other_tenant)

    admin_ids = set(
        queryset_for(
            OnboardingSessionAdmin, OnboardingSession, user, public_tenant
        ).values_list("id", flat=True)
    )
    manager_ids = set(
        OnboardingSession.objects.for_tenant(public_tenant).values_list("id", flat=True)
    )
    assert admin_ids == manager_ids


def test_question_admin_is_scoped_through_its_questionnaire(
    user, public_tenant, other_tenant
):
    """Review finding: Question had no scoping at all.

    "Scoping happens one level up" holds only while a question is reached
    through a questionnaire. The changelist is reachable directly, so staff
    would have seen every tenant's questions.
    """
    mine = make_question(questionnaire=make_questionnaire(tenant=public_tenant))
    theirs = make_question(questionnaire=make_questionnaire(tenant=other_tenant))

    visible = queryset_for(QuestionAdmin, Question, user, public_tenant)
    assert mine in visible
    assert theirs not in visible


def test_questionnaire_admin_hides_other_tenants(user, public_tenant, other_tenant):
    mine = make_questionnaire(tenant=public_tenant)
    theirs = make_questionnaire(tenant=other_tenant)

    visible = queryset_for(QuestionnaireAdmin, Questionnaire, user, public_tenant)
    assert mine in visible
    assert theirs not in visible


def test_a_superuser_sees_everything(admin_user, public_tenant, other_tenant):
    make_session(tenant=public_tenant)
    make_session(tenant=other_tenant)

    visible = queryset_for(
        OnboardingSessionAdmin, OnboardingSession, admin_user, public_tenant
    )
    assert visible.count() == 2


def test_a_request_without_a_tenant_sees_only_pre_tenant_rows(user, public_tenant):
    tenanted = make_session(tenant=public_tenant)
    legacy = make_session(company=make_company(), tenant=None)

    visible = queryset_for(OnboardingSessionAdmin, OnboardingSession, user, None)
    assert legacy in visible
    assert tenanted not in visible
