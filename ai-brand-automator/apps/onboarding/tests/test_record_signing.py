"""Signed meeting records · step 3 — signing.

Against the real database, the real endpoints and Django's in-memory mail
backend, which captures the actual messages: links and codes are read out of
the emails the way a signer would read them.

What is being protected:

- only the named person can sign, and only after proving the address is theirs;
- a signature binds to the content the signer was shown;
- nothing a signer does edits the text — they sign, remark or decline;
- no secret is stored, and a bad link says nothing about why it is bad.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.onboarding.models import RecordingStatus
from apps.onboarding.records import signing
from apps.onboarding.records.completion import expire_records
from apps.onboarding.records.models import (
    MeetingRecord,
    RecordEvent,
    RecordEventType,
    RecordSignatory,
    RecordStatus,
    SignatoryStatus,
)
from apps.onboarding.tests.factories import make_recording, make_session
from onboarding.models import Company
from tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

BASE = "/api/v1/onboarding"
PUBLIC = f"{BASE}/public/records/sign"

CLIENT_EMAIL = "maria@example.com"
AGENCY_EMAIL = "naveen@agency.test"


@pytest.fixture(autouse=True)
def _clear_throttles():
    """Throttle counters live in the cache and would leak between tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def public():
    """A browser with no login at all — the client's."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="Zorven Agency", schema_name="signing_a")


@pytest.fixture
def editor(api_client, tenant):
    user = User.objects.create_user(
        "naveen", AGENCY_EMAIL, "TestPass123!", first_name="Naveen", last_name="H"
    )
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.EDITOR)
    api_client.force_authenticate(user=user)
    return user


@pytest.fixture
def recording(tenant):
    company = Company.objects.create(
        tenant=tenant,
        name="Pomodoro",
        legal_name="Pomodoro Trattoria LLC",
        registered_address="14 Main Street, Austin",
        signatory_name="Maria Rossi",
        signatory_title="Owner",
        signatory_email=CLIENT_EMAIL,
    )
    return make_recording(
        session=make_session(company=company),
        status=RecordingStatus.SUMMARIZED,
        description="## Agreements\n- Launch budget split evenly.\n",
        transcript_clean="Naveen: Split evenly?\nMaria Rossi: Yes, agreed.",
        transcript_complete=True,
        transcript_missing_s=0,
    )


@pytest.fixture
def draft(api_client, editor, recording):
    response = api_client.post(
        f"{BASE}/recordings/{recording.pk}/records/", format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()


@pytest.fixture
def issued(api_client, draft):
    mail.outbox.clear()
    response = api_client.post(f"{BASE}/records/{draft['id']}/issue/", format="json")
    assert response.status_code == 200, response.content
    return response.json()


def mail_to(address: str, containing: str = ""):
    """The latest message to an address, as the recipient would find it."""
    found = [m for m in mail.outbox if m.to == [address] and containing in m.body]
    assert found, f"no email to {address} containing {containing!r}"
    return found[-1]


def link_in(message) -> str:
    return re.search(r"/sign/(\S+)", message.body).group(1)


def code_in(message) -> str:
    return re.search(r"^\s+(\d{6})\s*$", message.body, re.M).group(1)


def pdf_text(data: bytes) -> str:
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    assert "Meeting Record" in text, "no text was extracted from the PDF"
    return text


def allow_new_code(record_id) -> None:
    """Skip the one-minute wait between codes."""
    RecordSignatory.objects.filter(record_id=record_id).update(code_sent_at=None)


def open_session(public, token) -> dict:
    """Walk the link → code → verify steps, reading the code from the email."""
    sent = public.post(f"{PUBLIC}/{token}/code/", format="json")
    assert sent.status_code == 200, sent.content
    code = code_in(mail_to(CLIENT_EMAIL, "Your code"))
    verified = public.post(f"{PUBLIC}/{token}/verify/", {"code": code}, format="json")
    assert verified.status_code == 200, verified.content
    return verified.json()


def submit(public, token, opened, **body):
    payload = {"content_hash": opened["content_hash"], **body}
    return public.post(
        f"{PUBLIC}/{token}/submit/",
        payload,
        format="json",
        HTTP_X_SIGNING_SESSION=opened["session"],
    )


SIGN = {"action": "sign", "typed_name": "Maria Rossi", "consent": True}
REMARK = "Line 2: I agreed to an even split of the launch budget only."
WITH_REMARKS = {
    "action": "sign_with_remarks",
    "typed_name": "Maria Rossi",
    "consent": True,
    "remarks": REMARK,
}


def agency_signs(api_client, record, **overrides):
    body = {
        "action": "sign",
        "typed_name": "Naveen H",
        "consent": True,
        "content_hash": record["content_hash"],
        **overrides,
    }
    return api_client.post(f"{BASE}/records/{record['id']}/sign/", body, format="json")


@pytest.fixture
def client_token(issued):
    return link_in(mail_to(CLIENT_EMAIL, "ready for your signature"))


def client_row(record_id) -> RecordSignatory:
    return RecordSignatory.objects.get(record_id=record_id, email=CLIENT_EMAIL)


# ── Who signs ────────────────────────────────────────────────────────


def test_a_draft_starts_with_the_preparer_and_the_clients_signatory(draft):
    assert [(s["party"], s["name"], s["email"]) for s in draft["signatories"]] == [
        ("AGENCY", "Naveen H", AGENCY_EMAIL),
        ("CLIENT", "Maria Rossi", CLIENT_EMAIL),
    ]
    assert {s["status"] for s in draft["signatories"]} == {SignatoryStatus.PENDING}


def test_signatories_can_be_replaced_on_a_draft(api_client, draft):
    response = api_client.put(
        f"{BASE}/records/{draft['id']}/signatories/",
        {
            "signatories": [
                {"party": "AGENCY", "name": "Naveen H", "email": AGENCY_EMAIL},
                {"party": "CLIENT", "name": "Maria Rossi", "email": CLIENT_EMAIL},
                {
                    "party": "CLIENT",
                    "name": "Luca Rossi",
                    "email": "Luca@Example.com",
                    "title": "Chef",
                    "required": False,
                },
            ]
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    added = response.json()["signatories"][2]
    assert added["name"] == "Luca Rossi"
    assert added["email"] == "luca@example.com"
    assert added["required"] is False


@pytest.mark.parametrize(
    "entries, message",
    [
        ([{"party": "CLIENT", "name": "", "email": "a@b.co"}], "needs a name"),
        ([{"party": "CLIENT", "name": "A", "email": "nope"}], "valid email"),
        ([{"party": "OTHER", "name": "A", "email": "a@b.co"}], "agency or the client"),
        (
            [
                {"party": "CLIENT", "name": "A", "email": "a@b.co"},
                {"party": "AGENCY", "name": "B", "email": "A@B.co"},
            ],
            "listed twice",
        ),
    ],
)
def test_an_invalid_signatory_list_is_refused_and_changes_nothing(
    api_client, draft, entries, message
):
    response = api_client.put(
        f"{BASE}/records/{draft['id']}/signatories/",
        {"signatories": entries},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert message in response.json()["detail"]
    assert RecordSignatory.objects.filter(record_id=draft["id"]).count() == 2


def test_a_record_needs_a_signatory_for_each_party(api_client, draft):
    api_client.put(
        f"{BASE}/records/{draft['id']}/signatories/",
        {"signatories": [{"party": "AGENCY", "name": "N", "email": AGENCY_EMAIL}]},
        format="json",
    )

    response = api_client.post(f"{BASE}/records/{draft['id']}/issue/", format="json")

    assert response.status_code == 409, response.content
    item = {i["code"]: i for i in response.json()["readiness"]}["signatories"]
    assert item["ok"] is False
    assert item["message"] == "Add a required signatory for the client."


def test_signatories_are_fixed_once_issued(api_client, issued):
    response = api_client.put(
        f"{BASE}/records/{issued['id']}/signatories/",
        {"signatories": []},
        format="json",
    )

    assert response.status_code == 409, response.content
    assert RecordSignatory.objects.filter(record_id=issued["id"]).count() == 2


def test_who_signs_is_part_of_the_fingerprinted_content(issued):
    assert [s["email"] for s in issued["document"]["signatories"]] == [
        AGENCY_EMAIL,
        CLIENT_EMAIL,
    ]


# ── Issuing sends the links ──────────────────────────────────────────


def test_issuing_emails_each_signatory_their_own_link(issued):
    client_link = link_in(mail_to(CLIENT_EMAIL, "ready for your signature"))
    agency_link = link_in(mail_to(AGENCY_EMAIL, "ready for your signature"))

    assert client_link != agency_link
    assert len(client_link) >= 43
    assert issued["record_number"] in mail_to(CLIENT_EMAIL).body
    assert "Zorven Agency" in mail_to(CLIENT_EMAIL).body


def test_no_secret_is_stored_in_the_clear(issued, client_token, public):
    opened = open_session(public, client_token)
    code = code_in(mail_to(CLIENT_EMAIL, "Your code"))

    row = client_row(issued["id"])
    stored = " ".join(str(getattr(row, f.name)) for f in row._meta.fields)
    events = " ".join(
        str(e.detail) for e in RecordEvent.objects.filter(record_id=issued["id"])
    )

    for secret in (client_token, code, opened["session"]):
        assert secret not in stored
        assert secret not in events
    assert row.token_hash == signing.hash_secret(client_token)


def test_the_code_is_not_in_the_email_subject(issued, client_token, public):
    """Subjects show on lock screens and in notification previews."""
    public.post(f"{PUBLIC}/{client_token}/code/", format="json")
    message = mail_to(CLIENT_EMAIL, "Your code")

    assert code_in(message) not in message.subject


def test_a_record_expires_with_its_links(issued):
    record = MeetingRecord.objects.get(pk=issued["id"])
    row = client_row(record.pk)

    remaining = record.expires_at - timezone.now()
    assert timedelta(days=13) < remaining <= timedelta(days=14)
    assert abs((row.token_expires_at - record.expires_at).total_seconds()) < 5


def test_a_record_past_its_deadline_cannot_be_signed_before_the_sweep(
    api_client, public, client_token, issued
):
    """The daily job closes expired records; until it runs, the deadline binds."""
    opened = open_session(public, client_token)
    MeetingRecord.objects.filter(pk=issued["id"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    by_link = submit(public, client_token, opened, **SIGN)
    by_account = agency_signs(api_client, issued)

    assert by_link.json()["error"] == "not_open"
    assert by_account.json()["error"] == "not_open"
    assert client_row(issued["id"]).status == SignatoryStatus.PENDING


def test_a_reminder_link_never_outlives_the_record(api_client, issued):
    MeetingRecord.objects.filter(pk=issued["id"]).update(
        expires_at=timezone.now() + timedelta(days=1)
    )
    row = client_row(issued["id"])

    signing.issue_link(row)

    row.refresh_from_db()
    assert row.token_expires_at <= row.record.expires_at


# ── The link alone shows almost nothing ──────────────────────────────


def test_the_link_alone_shows_who_it_is_for_but_none_of_the_content(
    public, client_token, issued
):
    response = public.get(f"{PUBLIC}/{client_token}/")

    assert response.status_code == 200, response.content
    body = response.json()
    raw = response.content.decode()
    assert body["record_number"] == issued["record_number"]
    assert body["signatory"]["name"] == "Maria Rossi"
    assert body["signatory"]["email_hint"] == "m•••a@example.com"
    assert "document" not in body
    assert "content_hash" not in body
    assert CLIENT_EMAIL not in raw
    assert "Launch budget" not in raw


def test_opening_the_link_is_recorded(public, client_token, issued):
    public.get(f"{PUBLIC}/{client_token}/")

    event = RecordEvent.objects.get(
        record_id=issued["id"], event_type=RecordEventType.VIEWED
    )
    assert event.signatory.email == CLIENT_EMAIL


@pytest.mark.parametrize("path", ["", "code/", "verify/", "submit/"])
def test_an_unknown_and_an_expired_link_are_indistinguishable(
    public, client_token, issued, path
):
    """A caller must not learn whether a guess was close."""
    method = public.get if path == "" else public.post
    unknown = method(f"{PUBLIC}/{'x' * 43}/{path}", format="json")
    RecordSignatory.objects.filter(record_id=issued["id"]).update(
        token_expires_at=timezone.now() - timedelta(seconds=1)
    )
    expired = method(f"{PUBLIC}/{client_token}/{path}", format="json")

    assert unknown.status_code == 404
    assert expired.status_code == 404
    assert unknown.json() == expired.json()
    assert unknown.json()["error"] == "link_invalid"


def test_a_stale_login_header_does_not_block_a_signer(public, client_token):
    """A logged-out browser still sends its old token. The signing page must
    not answer 401 before it has even looked at the link."""
    response = public.get(
        f"{PUBLIC}/{client_token}/", HTTP_AUTHORIZATION="Bearer not-a-real-token"
    )

    assert response.status_code == 200, response.content


# ── The one-time code ────────────────────────────────────────────────


def test_a_correct_code_opens_the_record_to_read(public, client_token, issued):
    opened = open_session(public, client_token)

    assert opened["content_hash"] == issued["content_hash"]
    assert opened["document"]["agreements"]["items"][0]["text"] == (
        "Launch budget split evenly."
    )
    assert opened["can_sign"] is True
    assert opened["consent"]["text"].startswith("I agree to sign this document")
    assert len(opened["session"]) >= 43


def test_other_signatories_details_are_not_shown_to_a_signer(public, client_token):
    opened = open_session(public, client_token)

    assert [s["name"] for s in opened["signatories"]] == ["Naveen H", "Maria Rossi"]
    for entry in opened["signatories"]:
        assert "email" not in entry
        assert "ip_address" not in entry


def test_a_wrong_code_is_refused_and_counted(public, client_token, issued):
    public.post(f"{PUBLIC}/{client_token}/code/", format="json")

    response = public.post(
        f"{PUBLIC}/{client_token}/verify/", {"code": "not-it"}, format="json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"] == "code_incorrect"
    row = client_row(issued["id"])
    assert row.code_attempts == 1
    assert row.session_hash == ""


def test_after_five_wrong_codes_even_the_right_one_is_refused(
    public, client_token, issued
):
    """The count must survive each refusal, or it limits nothing."""
    public.post(f"{PUBLIC}/{client_token}/code/", format="json")
    code = code_in(mail_to(CLIENT_EMAIL, "Your code"))
    for _ in range(5):
        public.post(
            f"{PUBLIC}/{client_token}/verify/", {"code": "not-it"}, format="json"
        )

    response = public.post(
        f"{PUBLIC}/{client_token}/verify/", {"code": code}, format="json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["error"] == "code_locked"
    failed = RecordEvent.objects.filter(
        record_id=issued["id"], event_type=RecordEventType.CODE_FAILED
    )
    assert failed.count() == 5


def test_an_expired_code_is_refused(public, client_token, issued):
    public.post(f"{PUBLIC}/{client_token}/code/", format="json")
    code = code_in(mail_to(CLIENT_EMAIL, "Your code"))
    RecordSignatory.objects.filter(record_id=issued["id"]).update(
        code_expires_at=timezone.now() - timedelta(seconds=1)
    )

    response = public.post(
        f"{PUBLIC}/{client_token}/verify/", {"code": code}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"] == "code_expired"


def test_a_code_cannot_be_used_twice(public, client_token):
    open_session(public, client_token)
    code = code_in(mail_to(CLIENT_EMAIL, "Your code"))

    again = public.post(
        f"{PUBLIC}/{client_token}/verify/", {"code": code}, format="json"
    )

    assert again.status_code == 400
    assert again.json()["error"] == "code_required"


def test_a_second_code_cannot_be_requested_straight_away(public, client_token):
    """Otherwise the page is a way to flood someone's inbox."""
    first = public.post(f"{PUBLIC}/{client_token}/code/", format="json")
    before = len(mail.outbox)

    second = public.post(f"{PUBLIC}/{client_token}/code/", format="json")

    assert first.status_code == 200
    assert second.status_code == 429, second.content
    assert second.json()["error"] == "code_recent"
    assert len(mail.outbox) == before


def test_verifying_without_asking_for_a_code_is_refused(public, client_token):
    response = public.post(
        f"{PUBLIC}/{client_token}/verify/", {"code": "123456"}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"] == "code_required"


# ── Signing ──────────────────────────────────────────────────────────


def test_the_client_signs_without_an_account(public, client_token, issued):
    opened = open_session(public, client_token)

    response = submit(public, client_token, opened, **SIGN)

    assert response.status_code == 200, response.content
    row = client_row(issued["id"])
    assert row.status == SignatoryStatus.SIGNED
    assert row.typed_name == "Maria Rossi"
    assert row.method == "EMAIL_CODE"
    assert row.consent_version == "2026-11-draft-1"
    assert row.content_hash == issued["content_hash"]
    assert row.signed_at is not None
    record = MeetingRecord.objects.get(pk=issued["id"])
    assert record.status == RecordStatus.PARTIALLY_SIGNED


def test_a_signature_records_where_it_came_from(public, client_token, issued):
    opened = open_session(public, client_token)

    public.post(
        f"{PUBLIC}/{client_token}/submit/",
        {"content_hash": opened["content_hash"], **SIGN},
        format="json",
        HTTP_X_SIGNING_SESSION=opened["session"],
        HTTP_USER_AGENT="TestBrowser/1.0",
        HTTP_X_FORWARDED_FOR="203.0.113.7",
    )

    row = client_row(issued["id"])
    assert row.ip_address == "203.0.113.7"
    assert row.user_agent == "TestBrowser/1.0"


@pytest.mark.parametrize(
    "change, error",
    [
        ({"consent": False}, "consent_required"),
        ({"consent": "yes"}, "consent_required"),
        ({"typed_name": " "}, "name_required"),
        ({"action": "sign_with_remarks"}, "remarks_required"),
        ({"action": "approve"}, "invalid_action"),
        ({"content_hash": "0" * 64}, "content_mismatch"),
        ({"content_hash": ""}, "content_mismatch"),
    ],
)
def test_an_incomplete_signature_is_refused_and_records_nothing(
    public, client_token, issued, change, error
):
    opened = open_session(public, client_token)

    response = submit(public, client_token, opened, **{**SIGN, **change})

    assert response.status_code == 400, response.content
    assert response.json()["error"] == error
    row = client_row(issued["id"])
    assert row.status == SignatoryStatus.PENDING
    assert row.signed_at is None


def test_signing_needs_the_session_the_code_opened(public, client_token, issued):
    open_session(public, client_token)

    response = public.post(
        f"{PUBLIC}/{client_token}/submit/",
        {"content_hash": issued["content_hash"], **SIGN},
        format="json",
        HTTP_X_SIGNING_SESSION="guessed",
    )

    assert response.status_code == 401, response.content
    assert response.json()["error"] == "session_expired"


def test_the_link_alone_cannot_sign(public, client_token, issued):
    """Someone holding a forwarded email has the link and nothing else."""
    response = public.post(
        f"{PUBLIC}/{client_token}/submit/",
        {"content_hash": issued["content_hash"], **SIGN},
        format="json",
    )

    assert response.status_code == 401
    assert client_row(issued["id"]).status == SignatoryStatus.PENDING


def test_a_signing_session_is_spent_by_one_action(public, client_token):
    opened = open_session(public, client_token)
    assert submit(public, client_token, opened, **SIGN).status_code == 200

    replay = submit(public, client_token, opened, **SIGN)

    assert replay.status_code == 401


def test_a_person_cannot_sign_twice(public, client_token, issued):
    submit(public, client_token, open_session(public, client_token), **SIGN)
    allow_new_code(issued["id"])

    again = submit(public, client_token, open_session(public, client_token), **SIGN)

    assert again.status_code == 400, again.content
    assert again.json()["error"] == "already_acted"


def test_an_expired_session_cannot_sign(public, client_token, issued):
    opened = open_session(public, client_token)
    RecordSignatory.objects.filter(record_id=issued["id"]).update(
        session_expires_at=timezone.now() - timedelta(seconds=1)
    )

    assert submit(public, client_token, opened, **SIGN).status_code == 401


# ── The agency signs while logged in ─────────────────────────────────


def test_an_agency_signatory_signs_while_logged_in(api_client, issued):
    response = agency_signs(api_client, issued)

    assert response.status_code == 200, response.content
    row = RecordSignatory.objects.get(record_id=issued["id"], email=AGENCY_EMAIL)
    assert row.status == SignatoryStatus.SIGNED
    assert row.method == "ACCOUNT"
    assert row.typed_name == "Naveen H"
    assert response.json()["status"] == RecordStatus.PARTIALLY_SIGNED


def test_someone_not_named_on_the_record_cannot_sign_it(api_client, issued, tenant):
    """Which signatory you are comes from your account, never the request."""
    other = User.objects.create_user("other", "other@agency.test", "TestPass123!")
    Membership.objects.create(user=other, tenant=tenant, role=Membership.Role.ADMIN)
    api_client.force_authenticate(user=other)

    response = agency_signs(api_client, issued)

    assert response.status_code == 403, response.content
    assert response.json()["error"] == "not_a_signatory"
    signed = RecordSignatory.objects.filter(
        record_id=issued["id"], status=SignatoryStatus.SIGNED
    )
    assert signed.count() == 0


def test_the_agency_also_has_to_consent(api_client, issued):
    response = agency_signs(api_client, issued, consent=False)

    assert response.status_code == 400
    assert response.json()["error"] == "consent_required"


def test_the_record_tells_a_viewer_which_signatory_they_are(api_client, issued):
    """So the screen offers Sign only to someone who can, with the wording
    they will be agreeing to."""
    agency_id = RecordSignatory.objects.get(
        record_id=issued["id"], email=AGENCY_EMAIL
    ).pk

    assert issued["you"] == agency_id
    assert issued["consent"]["version"] == "2026-11-draft-1"
    assert "electronically" in issued["consent"]["text"]


def test_a_workspace_account_cannot_sign_for_the_client(api_client, tenant, issued):
    """A client signatory proves their address by code, even with an account."""
    user = User.objects.create_user("maria", CLIENT_EMAIL, "TestPass123!")
    Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.EDITOR)
    api_client.force_authenticate(user=user)

    response = agency_signs(api_client, issued, typed_name="Maria Rossi")
    detail = api_client.get(f"{BASE}/records/{issued['id']}/").json()

    assert response.status_code == 403
    assert response.json()["error"] == "not_a_signatory"
    assert detail["you"] is None
    assert client_row(issued["id"]).status == SignatoryStatus.PENDING


def test_a_member_who_is_not_signing_is_no_signatory(api_client, tenant, issued):
    other = User.objects.create_user("viewer", "viewer@agency.test", "TestPass123!")
    Membership.objects.create(user=other, tenant=tenant, role=Membership.Role.VIEWER)
    api_client.force_authenticate(user=other)

    response = api_client.get(f"{BASE}/records/{issued['id']}/")

    assert response.status_code == 200, response.content
    assert response.json()["you"] is None


# ── Completion ───────────────────────────────────────────────────────


@pytest.fixture
def completed(api_client, public, client_token, issued):
    assert agency_signs(api_client, issued).status_code == 200
    mail.outbox.clear()
    response = submit(public, client_token, open_session(public, client_token), **SIGN)
    assert response.status_code == 200, response.content
    return MeetingRecord.objects.get(pk=issued["id"])


def test_the_record_completes_when_every_required_person_has_signed(completed):
    assert completed.status == RecordStatus.COMPLETED
    assert completed.completed_at is not None
    events = RecordEvent.objects.filter(
        record=completed, event_type=RecordEventType.COMPLETED
    )
    assert events.count() == 1


def test_an_optional_signatory_does_not_hold_up_completion(api_client, public, draft):
    api_client.put(
        f"{BASE}/records/{draft['id']}/signatories/",
        {
            "signatories": [
                {"party": "AGENCY", "name": "Naveen H", "email": AGENCY_EMAIL},
                {"party": "CLIENT", "name": "Maria Rossi", "email": CLIENT_EMAIL},
                {
                    "party": "CLIENT",
                    "name": "Luca",
                    "email": "luca@example.com",
                    "required": False,
                },
            ]
        },
        format="json",
    )
    issued = api_client.post(
        f"{BASE}/records/{draft['id']}/issue/", format="json"
    ).json()
    token = link_in(mail_to(CLIENT_EMAIL, "ready for your signature"))
    agency_signs(api_client, issued)
    submit(public, token, open_session(public, token), **SIGN)

    assert MeetingRecord.objects.get(pk=draft["id"]).status == RecordStatus.COMPLETED


def test_everyone_is_sent_the_signed_pdf(completed):
    for address in (CLIENT_EMAIL, AGENCY_EMAIL):
        message = mail_to(address, "has been signed by everyone required")
        name, data, mimetype = message.attachments[0]
        assert name == f"{completed.record_number}.pdf"
        assert mimetype == "application/pdf"
        assert data.startswith(b"%PDF-")
        assert completed.content_hash in message.body


def test_the_final_pdf_is_fingerprinted_and_shows_the_signatures(completed):
    _, data, _ = mail_to(CLIENT_EMAIL, "has been signed").attachments[0]
    text = pdf_text(data)

    assert completed.pdf_hash == hashlib.sha256(data).hexdigest()
    assert "NOT FULLY SIGNED" not in text
    assert "Signature Maria Rossi" in text
    assert "Signature Naveen H" in text
    assert "Emailed link and one-time code" in text
    assert "Signed in to the workspace" in text
    assert "Identity confirmed by one-time code — Maria Rossi" in text
    assert "Completed — all required signatures collected" in text


def test_a_completed_record_downloads_without_a_watermark(api_client, completed):
    response = api_client.get(f"{BASE}/records/{completed.pk}/pdf/")
    text = pdf_text(response.content)

    assert response.status_code == 200
    assert "NOT FULLY SIGNED" not in text
    assert "Signature Maria Rossi" in text


def test_a_completed_record_can_no_longer_be_signed_or_voided(
    api_client, public, client_token, completed
):
    voided = api_client.post(
        f"{BASE}/records/{completed.pk}/void/", {"reason": "x"}, format="json"
    )
    allow_new_code(completed.pk)
    opened = open_session(public, client_token)

    assert voided.status_code == 409
    assert opened["can_sign"] is False
    assert submit(public, client_token, opened, **SIGN).json()["error"] == "not_open"


# ── Declining ────────────────────────────────────────────────────────


def test_declining_needs_a_reason(public, client_token, issued):
    opened = open_session(public, client_token)

    response = submit(public, client_token, opened, action="decline", reason=" ")

    assert response.status_code == 400
    assert response.json()["error"] == "reason_required"
    assert MeetingRecord.objects.get(pk=issued["id"]).status == RecordStatus.ISSUED


def test_declining_closes_the_record_and_tells_the_others(public, client_token, issued):
    opened = open_session(public, client_token)
    mail.outbox.clear()

    response = submit(
        public,
        client_token,
        opened,
        action="decline",
        reason="The budget figure is wrong: we said 15, not 50.",
    )

    assert response.status_code == 200, response.content
    record = MeetingRecord.objects.get(pk=issued["id"])
    assert record.status == RecordStatus.DECLINED
    assert record.snapshot == issued["document"]
    row = client_row(record.pk)
    assert row.status == SignatoryStatus.DECLINED
    assert row.decline_reason == "The budget figure is wrong: we said 15, not 50."
    assert "we said 15, not 50" in mail_to(AGENCY_EMAIL, "declined to sign").body
    assert [m.to for m in mail.outbox] == [[AGENCY_EMAIL]]


def test_an_optional_signatory_declining_leaves_the_record_open(
    api_client, public, draft
):
    api_client.put(
        f"{BASE}/records/{draft['id']}/signatories/",
        {
            "signatories": [
                {"party": "AGENCY", "name": "Naveen H", "email": AGENCY_EMAIL},
                {"party": "CLIENT", "name": "Maria Rossi", "email": CLIENT_EMAIL},
                {
                    "party": "CLIENT",
                    "name": "Luca",
                    "email": "luca@example.com",
                    "required": False,
                },
            ]
        },
        format="json",
    )
    issued = api_client.post(
        f"{BASE}/records/{draft['id']}/issue/", format="json"
    ).json()
    luca = link_in(mail_to("luca@example.com", "ready for your signature"))
    sent = public.post(f"{PUBLIC}/{luca}/code/", format="json")
    assert sent.status_code == 200, sent.content
    code = code_in(mail_to("luca@example.com", "Your code"))
    opened = public.post(f"{PUBLIC}/{luca}/verify/", {"code": code}, format="json")

    declined = submit(public, luca, opened.json(), action="decline", reason="Not me.")

    assert declined.status_code == 200, declined.content
    assert MeetingRecord.objects.get(pk=draft["id"]).status == RecordStatus.ISSUED
    maria = link_in(mail_to(CLIENT_EMAIL, "ready for your signature"))
    agency_signs(api_client, issued)
    submit(public, maria, open_session(public, maria), **SIGN)
    assert MeetingRecord.objects.get(pk=draft["id"]).status == RecordStatus.COMPLETED


def test_a_declined_record_can_be_superseded_with_the_same_signatories(
    api_client, public, client_token, issued
):
    opened = open_session(public, client_token)
    submit(public, client_token, opened, action="decline", reason="Wrong figure.")

    response = api_client.post(
        f"{BASE}/records/{issued['id']}/supersede/", format="json"
    )

    assert response.status_code == 201, response.content
    successor = response.json()
    assert successor["version"] == 2
    assert [(s["email"], s["status"]) for s in successor["signatories"]] == [
        (AGENCY_EMAIL, SignatoryStatus.PENDING),
        (CLIENT_EMAIL, SignatoryStatus.PENDING),
    ]


# ── Remarks ──────────────────────────────────────────────────────────


def test_signing_with_remarks_records_them_without_touching_the_text(
    public, client_token, issued
):
    opened = open_session(public, client_token)

    response = submit(public, client_token, opened, **WITH_REMARKS)

    assert response.status_code == 200, response.content
    record = MeetingRecord.objects.get(pk=issued["id"])
    assert record.snapshot == issued["document"]
    assert record.content_hash == issued["content_hash"]
    row = client_row(record.pk)
    assert row.remarks == REMARK
    assert row.status == SignatoryStatus.SIGNED


def test_a_plain_signature_carries_no_remarks_even_if_some_were_sent(
    public, client_token, issued
):
    opened = open_session(public, client_token)

    submit(public, client_token, opened, **SIGN, remarks="ignored")

    assert client_row(issued["id"]).remarks == ""


def test_a_remark_made_after_someone_signed_must_be_acknowledged_by_them(
    api_client, public, client_token, issued
):
    """The agency signed text with no remarks on it. It cannot be held to a
    record that later gained one without seeing it."""
    agency_signs(api_client, issued)
    mail.outbox.clear()

    submit(public, client_token, open_session(public, client_token), **WITH_REMARKS)

    record = MeetingRecord.objects.get(pk=issued["id"])
    assert record.status == RecordStatus.PARTIALLY_SIGNED
    assert REMARK in mail_to(AGENCY_EMAIL, "with remarks").body
    detail = api_client.get(f"{BASE}/records/{issued['id']}/").json()
    agency_id = str(detail["signatories"][0]["id"])
    assert detail["remarks_to_acknowledge"] == {agency_id: ["Maria Rossi"]}

    done = agency_signs(api_client, issued, action="acknowledge_remarks")

    assert done.status_code == 200, done.content
    assert done.json()["status"] == RecordStatus.COMPLETED
    acknowledged = RecordEvent.objects.filter(
        record=record, event_type=RecordEventType.REMARKS_ACKNOWLEDGED
    )
    assert acknowledged.count() == 1


def test_someone_who_signs_after_a_remark_has_already_seen_it(
    api_client, public, client_token, issued
):
    submit(public, client_token, open_session(public, client_token), **WITH_REMARKS)

    response = agency_signs(api_client, issued)

    assert response.json()["status"] == RecordStatus.COMPLETED


def test_there_is_nothing_to_acknowledge_without_a_new_remark(api_client, issued):
    agency_signs(api_client, issued)

    response = agency_signs(api_client, issued, action="acknowledge_remarks")

    assert response.status_code == 400
    assert response.json()["error"] == "nothing_to_acknowledge"


def test_remarks_are_printed_on_the_final_record(
    api_client, public, client_token, issued
):
    submit(public, client_token, open_session(public, client_token), **WITH_REMARKS)
    agency_signs(api_client, issued)

    _, data, _ = mail_to(CLIENT_EMAIL, "has been signed").attachments[0]
    text = pdf_text(data).replace("\n", " ")

    assert "I agreed to an even split of the launch budget" in text


# ── Reminders, voiding, expiry ───────────────────────────────────────


def test_a_reminder_sends_a_new_link_and_retires_the_old_one(
    api_client, public, client_token, issued
):
    mail.outbox.clear()

    response = api_client.post(f"{BASE}/records/{issued['id']}/remind/", format="json")

    assert response.status_code == 200, response.content
    assert response.json()["sent"] == 2
    message = mail_to(CLIENT_EMAIL, "A reminder")
    assert message.subject.startswith("Reminder:")
    new_token = link_in(message)
    assert new_token != client_token
    assert public.get(f"{PUBLIC}/{client_token}/").status_code == 404
    assert public.get(f"{PUBLIC}/{new_token}/").status_code == 200


def test_a_reminder_skips_those_who_have_signed(api_client, issued):
    agency_signs(api_client, issued)
    mail.outbox.clear()

    response = api_client.post(f"{BASE}/records/{issued['id']}/remind/", format="json")

    assert response.json()["sent"] == 1
    assert [m.to for m in mail.outbox] == [[CLIENT_EMAIL]]


def test_a_draft_cannot_be_reminded(api_client, draft):
    response = api_client.post(f"{BASE}/records/{draft['id']}/remind/", format="json")

    assert response.status_code == 409
    assert response.json()["error"] == "not_open"


def test_a_voided_record_can_no_longer_be_signed(
    api_client, public, client_token, issued
):
    opened = open_session(public, client_token)
    api_client.post(
        f"{BASE}/records/{issued['id']}/void/", {"reason": "Typo."}, format="json"
    )

    response = submit(public, client_token, opened, **SIGN)

    assert response.status_code == 400
    assert response.json()["error"] == "not_open"


def test_records_past_their_date_expire_once(issued):
    MeetingRecord.objects.filter(pk=issued["id"]).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )

    assert expire_records() == 1
    record = MeetingRecord.objects.get(pk=issued["id"])
    assert record.status == RecordStatus.EXPIRED
    expired = RecordEvent.objects.filter(
        record=record, event_type=RecordEventType.EXPIRED
    )
    assert expired.count() == 1
    assert expire_records() == 0


def test_a_record_still_in_date_is_left_alone(issued):
    assert expire_records() == 0
    assert MeetingRecord.objects.get(pk=issued["id"]).status == RecordStatus.ISSUED


def test_a_failed_email_does_not_undo_the_issue(api_client, draft, settings):
    """An issued record is issued whether or not the mail server answered;
    the failure is in the audit trail so someone can send a reminder."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = "127.0.0.1"
    settings.EMAIL_PORT = 1

    response = api_client.post(f"{BASE}/records/{draft['id']}/issue/", format="json")

    assert response.status_code == 200, response.content
    assert response.json()["status"] == RecordStatus.ISSUED
    failed = RecordEvent.objects.filter(
        record_id=draft["id"], event_type=RecordEventType.EMAIL_FAILED
    )
    assert failed.count() == 2


# ── Small things that matter ─────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "email, masked",
    [
        ("maria@example.com", "m•••a@example.com"),
        ("al@example.com", "a•••@example.com"),
        ("x@example.com", "x•••@example.com"),
    ],
)
def test_an_address_is_masked_enough_to_recognise_not_to_learn(email, masked):
    assert signing.mask_email(email) == masked


@pytest.mark.unit
def test_tokens_are_long_and_never_repeat():
    tokens = {signing.new_token() for _ in range(500)}

    assert len(tokens) == 500
    assert min(len(t) for t in tokens) >= 43


@pytest.mark.unit
def test_codes_are_always_six_digits():
    codes = [signing.new_code() for _ in range(500)]

    assert {len(c) for c in codes} == {6}
    assert {c.isdigit() for c in codes} == {True}
