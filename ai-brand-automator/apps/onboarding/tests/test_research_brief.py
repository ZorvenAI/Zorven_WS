"""C-02 PR 3 · durable ResearchBrief storage (AC-2's Interface half).

The agent already caches briefs in Redis for an hour, which covers an operator
tuning question count in one sitting. AC-2 also says "or opens the Onboarding
Interface", and a TTL'd cache in another service cannot serve that.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.onboarding.models import ResearchBrief
from apps.onboarding.text import normalise_company_name
from onboarding.models import Company
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

TOKEN = "dev-service-token"
UPSERT = "/api/v1/onboarding/research-briefs/upsert/"


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="C02 Co", schema_name="c02_brief")


def good_brief(**overrides):
    brief = {
        "company_name": "Kalyani Roasters",
        "facts": [
            {"statement": "Founded 2016.", "source_url": "https://k.example/about"}
        ],
        "competitors_seen": ["Blue Tokai"],
        "digital_presence": {"website": "https://k.example"},
        "open_unknowns": ["What is their AOV?", "Who is the buyer?"],
        "degraded": False,
        "degraded_reason": "",
        "sources": ["https://k.example/about"],
    }
    brief.update(overrides)
    return brief


# ── The internal write endpoint ──────────────────────────────────────


def test_the_agent_can_store_a_brief(api_client, tenant):
    response = api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 201, response.content
    row = ResearchBrief.objects.get()
    assert row.company_name == "Kalyani Roasters"
    assert row.normalised_name == "kalyani roasters"
    assert row.fact_count == 1
    assert row.unknown_count == 2


def test_a_write_without_the_token_is_refused(api_client):
    response = api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
    )

    assert response.status_code == 403
    assert not ResearchBrief.objects.exists()


def test_a_write_with_a_wrong_token_is_refused(api_client):
    response = api_client.post(
        UPSERT,
        {"company_name": "X", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN="nope",
    )

    assert response.status_code == 403


def test_re_running_research_updates_in_place(api_client, tenant):
    """Upsert, not accumulate. Versioning here would put a second,
    differently-shaped history alongside Questionnaire's."""
    api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )
    second = api_client.post(
        UPSERT,
        {
            "company_name": "Kalyani Roasters Pvt. Ltd.",
            "brief": good_brief(facts=[], open_unknowns=["a", "b", "c"]),
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert second.status_code == 200
    assert ResearchBrief.objects.count() == 1, "the retyped name made a second row"
    row = ResearchBrief.objects.get()
    assert row.fact_count == 0
    assert row.unknown_count == 3


def test_a_degraded_brief_never_overwrites_stored_research(api_client, tenant):
    """The rule the agent applies to its Redis cache, enforced here too so a
    future caller cannot bypass it.

    A degraded brief is the *absence* of research. Letting one land would mean
    a brief Tavily outage erases findings that cost money to obtain.
    """
    api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    response = api_client.post(
        UPSERT,
        {
            "company_name": "Kalyani Roasters",
            "brief": good_brief(
                facts=[], degraded=True, degraded_reason="tavily breaker open"
            ),
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 200
    assert response.json()["stored"] is False
    row = ResearchBrief.objects.get()
    assert row.degraded is False
    assert row.fact_count == 1, "real research was overwritten"


def test_a_degraded_brief_reports_what_is_actually_stored(api_client, tenant):
    """So the caller does not assume its copy landed."""
    api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )
    response = api_client.post(
        UPSERT,
        {
            "company_name": "Kalyani Roasters",
            "brief": good_brief(degraded=True, degraded_reason="x"),
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.json()["existing"]["fact_count"] == 1


def test_a_degraded_brief_with_nothing_stored_creates_nothing(api_client, tenant):
    response = api_client.post(
        UPSERT,
        {
            "company_name": "Unknown Co",
            "brief": good_brief(degraded=True, degraded_reason="no key"),
        },
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 200
    assert response.json()["existing"] is None
    assert not ResearchBrief.objects.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"brief": {"facts": []}},
        {"company_name": "X"},
        {"company_name": "", "brief": {}},
        {"company_name": "X", "brief": "not-an-object"},
    ],
)
def test_a_malformed_write_is_refused(api_client, payload, tenant):
    response = api_client.post(
        UPSERT,
        payload,
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert response.status_code == 400
    assert not ResearchBrief.objects.exists()


# ── Reading it back (AC-2) ───────────────────────────────────────────


def test_a_viewer_can_read_a_stored_brief(api_client, tenant):
    """§15 puts SKL-OIA-01 at DENY for VIEWER, but that governs *invoking*
    research — spending money on Tavily — not reading one that exists.
    §15's own VIEW_RESULT verdict is this distinction."""
    user = User.objects.create_user("c02_viewer", "v@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.VIEWER)
    ResearchBrief.objects.create(
        tenant=tenant,
        company_name="Kalyani Roasters",
        normalised_name="kalyani roasters",
        brief=good_brief(),
        fact_count=1,
    )

    api_client.force_authenticate(user=user)
    response = api_client.get("/api/v1/onboarding/research-briefs/")

    assert response.status_code == 200


def test_a_brief_is_found_by_a_differently_typed_name(api_client, tenant):
    """The Interface looks up by whatever the operator typed. Matching the raw
    string would make the lookup depend on their punctuation."""
    user = User.objects.create_user("c02_look", "l@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.VIEWER)
    ResearchBrief.objects.create(
        tenant=tenant,
        company_name="Kalyani Roasters",
        normalised_name="kalyani roasters",
        brief=good_brief(),
    )

    api_client.force_authenticate(user=user)
    response = api_client.get(
        "/api/v1/onboarding/research-briefs/",
        {"company_name": "  KALYANI ROASTERS PVT. LTD. "},
    )

    results = response.json()
    rows = results["results"] if isinstance(results, dict) else results
    assert len(rows) == 1


def test_the_read_surface_is_read_only(api_client, tenant):
    user = User.objects.create_user("c02_ro", "ro@test.com", "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.ADMIN)
    api_client.force_authenticate(user=user)

    before = ResearchBrief.objects.count()
    response = api_client.post(
        "/api/v1/onboarding/research-briefs/",
        {"company_name": "X", "brief": {}},
        format="json",
    )

    # 405 specifically: the viewset exposes no create action, so DRF refuses
    # the method. Accepting (403, 405) — as this did — would also pass if the
    # surface became writable and merely denied this user, which is a
    # different and weaker guarantee.
    assert response.status_code == 405, response.content
    assert ResearchBrief.objects.count() == before


# ── The constraints ──────────────────────────────────────────────────


def test_two_briefs_for_one_business_and_tenant_are_refused(tenant):
    ResearchBrief.objects.create(
        tenant=tenant,
        company_name="Kalyani",
        normalised_name="kalyani",
        brief={},
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ResearchBrief.objects.create(
            tenant=tenant,
            company_name="Kalyani",
            normalised_name="kalyani",
            brief={},
        )


def test_duplicate_pre_tenant_rows_are_also_refused():
    """PostgreSQL treats NULLs as distinct, so a single constraint over a
    nullable tenant would silently permit unlimited duplicates here — the case
    that would otherwise slip through review."""
    ResearchBrief.objects.create(
        tenant=None, company_name="Kalyani", normalised_name="kalyani", brief={}
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ResearchBrief.objects.create(
            tenant=None, company_name="Kalyani", normalised_name="kalyani", brief={}
        )


def test_the_same_business_may_exist_for_two_tenants(tenant):
    other = Tenant.objects.create(name="Other", schema_name="c02_other")
    ResearchBrief.objects.create(
        tenant=tenant, company_name="Kalyani", normalised_name="kalyani", brief={}
    )

    ResearchBrief.objects.create(
        tenant=other, company_name="Kalyani", normalised_name="kalyani", brief={}
    )

    assert ResearchBrief.objects.count() == 2


def test_a_degraded_row_must_state_its_reason(tenant):
    """A row flagged degraded with no reason tells an operator their questions
    are thin without saying why, which is the half-answer AC-3 rules out."""
    with pytest.raises(IntegrityError), transaction.atomic():
        ResearchBrief.objects.create(
            tenant=tenant,
            company_name="Kalyani",
            normalised_name="kalyani",
            brief={},
            degraded=True,
            degraded_reason="",
        )


def test_a_brief_can_be_attached_to_a_session(tenant):
    """Prep precedes the session, so the FK is nullable — but it must attach
    once one exists, or the Interface cannot reach the brief."""
    from apps.onboarding.models import OnboardingSession

    company = Company.objects.create(tenant=tenant, name="Kalyani")
    session = OnboardingSession.objects.create(tenant=tenant, company=company)

    row = ResearchBrief.objects.create(
        tenant=tenant,
        session=session,
        company_name="Kalyani",
        normalised_name="kalyani",
        brief={},
    )

    assert session.research_briefs.get() == row


# ── The normalisation must match the agent's ─────────────────────────


@pytest.mark.parametrize(
    "written",
    [
        "Kalyani Roasters",
        "kalyani roasters",
        "  Kalyani   Roasters  ",
        "Kalyani Roasters Pvt. Ltd.",
        "KALYANI ROASTERS PRIVATE LIMITED",
    ],
)
def test_the_shared_normalisation_corpus(written):
    """The same corpus runs in
    ``onboarding-intelligence-agent-svc/tests/test_research_business.py``.

    The two implementations are duplicated because the services are separate
    deployables with no common package. If they drift, the agent stores a
    brief under one key and the Interface looks for another — the operator is
    told there is no research when there is. Running one corpus on both sides
    is what makes a drift fail a test rather than a demo.
    """
    assert normalise_company_name(written) == "kalyani roasters"


# ── Tenant attribution through the endpoint (the C-03 finding) ───────


def test_the_brief_is_attributed_to_the_header_tenant(api_client, tenant):
    """The bug this file did not catch when it shipped.

    Every service-endpoint test here sent a token and no tenant, and the view
    read ``request.tenant``. Settings put DefaultTenantMiddleware in the
    chain, which resolves an unmatched host — always, for an internal call —
    to the *public* tenant. So every brief the agent wrote was attributed to
    the public tenant, and no test noticed, because the read-side tests built
    their rows through the ORM with an explicit tenant and never went through
    the endpoint at all.
    """
    api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=str(tenant.pk),
    )

    assert ResearchBrief.objects.get().tenant == tenant


def test_two_tenants_researching_the_same_business_do_not_collide(api_client, tenant):
    """The concrete harm. ResearchBrief is unique on
    ``(tenant, normalised_name)``. With both writes landing on the public
    tenant, the second tenant's research silently overwrote the first's — and
    each could read the other's.
    """
    other = Tenant.objects.create(name="Other", schema_name="c02_other_tenant")

    for owner, fact in ((tenant, "First tenant's finding."), (other, "Second's.")):
        api_client.post(
            UPSERT,
            {
                "company_name": "Kalyani Roasters",
                "brief": good_brief(
                    facts=[{"statement": fact, "source_url": "https://k.example/a"}]
                ),
            },
            format="json",
            HTTP_X_SERVICE_TOKEN=TOKEN,
            HTTP_X_TENANT_ID=str(owner.pk),
        )

    assert ResearchBrief.objects.count() == 2, "one tenant overwrote the other"
    assert {b.tenant for b in ResearchBrief.objects.all()} == {tenant, other}


def test_a_write_without_the_tenant_header_is_refused(api_client):
    """Rejected rather than defaulted. Every fallback available here is wrong:
    the public tenant mixes tenants together, and None makes the row visible
    to all of them."""
    response = api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
    )

    assert response.status_code == 400
    assert "X-Tenant-ID" in response.json()["error"]
    assert not ResearchBrief.objects.exists()


def test_a_write_naming_an_unknown_tenant_is_refused(api_client):
    response = api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID="999999",
    )

    assert response.status_code == 400
    assert not ResearchBrief.objects.exists()


@pytest.mark.parametrize("bad", ["not-a-number", "1; DROP TABLE", "٣"])
def test_a_malformed_tenant_header_is_a_400_not_a_500(api_client, bad):
    """The same guard on the brief endpoint — it shares _service_tenant."""
    response = api_client.post(
        UPSERT,
        {"company_name": "Kalyani Roasters", "brief": good_brief()},
        format="json",
        HTTP_X_SERVICE_TOKEN=TOKEN,
        HTTP_X_TENANT_ID=bad,
    )

    assert response.status_code == 400, response.content
    assert not ResearchBrief.objects.exists()
