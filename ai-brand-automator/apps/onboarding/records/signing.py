"""Signing a meeting record.

What makes a signature here worth something, in the order a dispute would
test it:

- **Intent** — an explicit action plus the signer's typed name.
- **Consent** to sign electronically — required, and its wording is versioned.
- **Attribution** — a single-use emailed link, then a one-time code sent to
  the same address, plus the address and browser the signature came from.
  An agency user signs while logged in instead.
- **Integrity** — the signer sends back the fingerprint they were shown, and
  a signature is refused if it is not the record's.

No secret is stored. The link token, the code and the signing session are
kept as SHA-256 hashes only, and each is compared in constant time.

Text is never edited. A signer who disagrees signs *with remarks* or
declines; a remark made after someone else has signed must be acknowledged by
them before the record completes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.onboarding.records.clauses import CONSENT_VERSION
from apps.onboarding.records.lifecycle import RecordError, _locked, log_event
from apps.onboarding.records.models import (
    MeetingRecord,
    RecordEventType,
    RecordSignatory,
    RecordStatus,
    SignatoryParty,
    SignatoryStatus,
)

CODE_TTL = timedelta(minutes=10)
CODE_COOLDOWN = timedelta(seconds=60)
CODE_MAX_ATTEMPTS = 5
SESSION_TTL = timedelta(minutes=30)

OPEN_STATUSES = (RecordStatus.ISSUED, RecordStatus.PARTIALLY_SIGNED)

SIGN = "sign"
SIGN_WITH_REMARKS = "sign_with_remarks"
DECLINE = "decline"
ACKNOWLEDGE = "acknowledge_remarks"
ACTIONS = (SIGN, SIGN_WITH_REMARKS, DECLINE, ACKNOWLEDGE)


def link_ttl() -> timedelta:
    return timedelta(days=int(getattr(settings, "RECORDS_LINK_TTL_DAYS", 14)))


# ── Secrets ──────────────────────────────────────────────────────────


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _matches(value: str, stored_hash: str) -> bool:
    """Constant-time, and never true against an empty stored hash."""
    return bool(stored_hash) and hmac.compare_digest(hash_secret(value), stored_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def mask_email(email: str) -> str:
    """``maria@example.com`` → ``m•••a@example.com``.

    Enough for the right person to recognise their address, not enough for
    someone holding a forwarded link to learn it.
    """
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}•••@{domain}"
    return f"{local[0]}•••{local[-1]}@{domain}"


# ── Who signs ────────────────────────────────────────────────────────


def default_signatories(record: MeetingRecord, user=None) -> list[dict[str, Any]]:
    """A starting list: the preparer and the client's authorised signatory.

    Only entries that are complete. A half-filled signatory would look
    settled and fail at issue instead.
    """
    entries: list[dict[str, Any]] = []
    email = (getattr(user, "email", "") or "").strip()
    if email:
        entries.append(
            {
                "party": SignatoryParty.AGENCY,
                "name": (user.get_full_name() or user.get_username()).strip(),
                "title": "",
                "email": email,
            }
        )
    company = record.session.company
    name = (getattr(company, "signatory_name", None) or "").strip()
    client_email = (getattr(company, "signatory_email", None) or "").strip()
    if name and client_email:
        entries.append(
            {
                "party": SignatoryParty.CLIENT,
                "name": name,
                "title": (getattr(company, "signatory_title", None) or "").strip(),
                "email": client_email,
            }
        )
    return entries


def _clean_signatories(entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise RecordError("invalid_signatories", "signatories must be a list.")
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"Signatory {index + 1}"
        if not isinstance(entry, dict):
            raise RecordError("invalid_signatories", f"{label} is invalid.")
        party = str(entry.get("party") or "").upper()
        name = str(entry.get("name") or "").strip()
        email = str(entry.get("email") or "").strip().lower()
        if party not in SignatoryParty.values:
            raise RecordError(
                "invalid_signatories",
                f"{label} must be for the agency or the client.",
            )
        if not name:
            raise RecordError("invalid_signatories", f"{label} needs a name.")
        try:
            validate_email(email)
        except ValidationError:
            raise RecordError(
                "invalid_signatories", f"{label} needs a valid email address."
            ) from None
        if email in seen:
            raise RecordError(
                "invalid_signatories",
                f"{email} is listed twice. Each signatory needs their own "
                "address: it is how their signature is attributed to them.",
            )
        seen.add(email)
        cleaned.append(
            {
                "party": party,
                "name": name[:255],
                "title": str(entry.get("title") or "").strip()[:255],
                "email": email,
                "required": entry.get("required") is not False,
                "order": index,
            }
        )
    return cleaned


@transaction.atomic
def set_signatories(record: MeetingRecord, entries: Any) -> list[RecordSignatory]:
    """Replace a draft's signatories. Fixed once the record is issued."""
    record = _locked(record)
    if record.status != RecordStatus.DRAFT:
        raise RecordError(
            "not_draft",
            f"{record.record_number} is {record.status}. Signatories can only "
            "be changed on a draft.",
        )
    cleaned = _clean_signatories(entries)
    record.signatories.all().delete()
    return RecordSignatory.objects.bulk_create(
        [RecordSignatory(tenant=record.tenant, record=record, **e) for e in cleaned]
    )


def signatory_snapshot(record: MeetingRecord) -> list[dict[str, Any]]:
    """Who is to sign, for the frozen content. Binding the list into the
    fingerprint means it cannot change after issue without showing."""
    return [
        {
            "party": s.party,
            "name": s.name,
            "title": s.title,
            "email": s.email,
            "required": s.required,
        }
        for s in record.signatories.all()
    ]


# ── Links, codes, sessions ───────────────────────────────────────────


def issue_link(signatory: RecordSignatory) -> str:
    """A fresh signing link token. Replaces any earlier one."""
    token = new_token()
    signatory.token_hash = hash_secret(token)
    expires = timezone.now() + link_ttl()
    # A link never outlives the record it signs.
    if signatory.record.expires_at and signatory.record.expires_at < expires:
        expires = signatory.record.expires_at
    signatory.token_expires_at = expires
    signatory.save(update_fields=["token_hash", "token_expires_at", "updated_at"])
    return token


def resolve_token(token: str) -> RecordSignatory | None:
    """The signatory a link belongs to, or nothing.

    Unknown and expired are the same answer on purpose: a caller must not be
    able to tell a wrong token from a stale one.
    """
    if not token or len(token) > 200:
        return None
    signatory = (
        RecordSignatory.objects.select_related(
            "record", "record__session", "record__session__company", "record__tenant"
        )
        .filter(token_hash=hash_secret(token))
        .first()
    )
    if signatory is None:
        return None
    if not signatory.token_expires_at or signatory.token_expires_at < timezone.now():
        return None
    if signatory.record.status == RecordStatus.DRAFT:
        return None
    return signatory


@transaction.atomic
def start_code(signatory: RecordSignatory, *, ip_address=None) -> str | None:
    """A new one-time code, or nothing while the last one is too recent."""
    signatory = RecordSignatory.objects.select_for_update().get(pk=signatory.pk)
    now = timezone.now()
    if signatory.code_sent_at and now - signatory.code_sent_at < CODE_COOLDOWN:
        return None
    code = new_code()
    signatory.code_hash = hash_secret(code)
    signatory.code_expires_at = now + CODE_TTL
    signatory.code_sent_at = now
    signatory.code_attempts = 0
    signatory.save(
        update_fields=[
            "code_hash",
            "code_expires_at",
            "code_sent_at",
            "code_attempts",
            "updated_at",
        ]
    )
    log_event(
        signatory.record,
        RecordEventType.CODE_SENT,
        signatory=signatory,
        ip_address=ip_address,
    )
    return code


def verify_code(signatory: RecordSignatory, code: str, *, ip_address=None) -> str:
    """Exchange a correct code for a signing session. Raises on anything else.

    Every attempt is counted, and the count is committed before a wrong code
    is reported: raising inside the transaction would roll back the very
    counter that limits guessing. So the transaction returns its verdict and
    the refusal is raised after it.
    """
    refusal: RecordError | None = None
    session = ""

    with transaction.atomic():
        signatory = RecordSignatory.objects.select_for_update().get(pk=signatory.pk)
        now = timezone.now()
        if not signatory.code_hash or not signatory.code_expires_at:
            refusal = RecordError("code_required", "Request a code first.")
        elif signatory.code_expires_at < now:
            refusal = RecordError(
                "code_expired", "That code has expired. Request a new one."
            )
        elif signatory.code_attempts >= CODE_MAX_ATTEMPTS:
            refusal = RecordError(
                "code_locked", "Too many incorrect attempts. Request a new code."
            )
        elif not _matches(str(code or "").strip(), signatory.code_hash):
            signatory.code_attempts += 1
            signatory.save(update_fields=["code_attempts", "updated_at"])
            log_event(
                signatory.record,
                RecordEventType.CODE_FAILED,
                signatory=signatory,
                ip_address=ip_address,
                attempt=signatory.code_attempts,
            )
            refusal = RecordError("code_incorrect", "That code is not correct.")
        else:
            session = new_token()
            signatory.code_hash = ""
            signatory.code_expires_at = None
            signatory.session_hash = hash_secret(session)
            signatory.session_expires_at = now + SESSION_TTL
            signatory.save(
                update_fields=[
                    "code_hash",
                    "code_expires_at",
                    "session_hash",
                    "session_expires_at",
                    "updated_at",
                ]
            )
            log_event(
                signatory.record,
                RecordEventType.CODE_VERIFIED,
                signatory=signatory,
                ip_address=ip_address,
            )

    if refusal is not None:
        raise refusal
    return session


def session_is_valid(signatory: RecordSignatory, session: str) -> bool:
    return bool(
        session
        and signatory.session_expires_at
        and signatory.session_expires_at >= timezone.now()
        and _matches(session, signatory.session_hash)
    )


# ── Remarks and completion ───────────────────────────────────────────


def remarks_of(record: MeetingRecord) -> list[RecordSignatory]:
    return [s for s in record.signatories.all() if s.remarks.strip() and s.signed_at]


def pending_acknowledgements(
    record: MeetingRecord,
) -> dict[int, list[RecordSignatory]]:
    """For each signatory who has signed: the remarks made after they did,
    which they have not yet acknowledged.

    Someone who signs *after* a remark saw it on the page they signed, so
    signing is their acknowledgement.
    """
    remarks = remarks_of(record)
    owed: dict[int, list[RecordSignatory]] = {}
    for signer in record.signatories.all():
        if signer.status != SignatoryStatus.SIGNED or not signer.signed_at:
            continue
        seen_until = max(
            signer.signed_at, signer.remarks_acknowledged_at or signer.signed_at
        )
        unseen = [r for r in remarks if r.pk != signer.pk and r.signed_at > seen_until]
        if unseen:
            owed[signer.pk] = unseen
    return owed


def _is_complete(record: MeetingRecord) -> bool:
    required = [s for s in record.signatories.all() if s.required]
    return (
        bool(required)
        and all(s.status == SignatoryStatus.SIGNED for s in required)
        and not pending_acknowledgements(record)
    )


@transaction.atomic
def act(
    signatory: RecordSignatory,
    action: str,
    *,
    method: str,
    content_hash: str = "",
    typed_name: str = "",
    consent: bool = False,
    remarks: str = "",
    reason: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
    user=None,
) -> MeetingRecord:
    """Sign, sign with remarks, decline, or acknowledge others' remarks.

    Returns the record in its new state. ``record.just_completed`` is set
    when this action was the one that completed it.
    """
    record = _locked(signatory.record)
    signatory = RecordSignatory.objects.select_for_update().get(pk=signatory.pk)
    record.just_completed = False

    if action not in ACTIONS:
        raise RecordError("invalid_action", "Unknown action.")
    if record.status not in OPEN_STATUSES:
        raise RecordError(
            "not_open",
            f"{record.record_number} is {record.get_status_display().lower()} "
            "and can no longer be signed.",
        )
    # The daily expiry job may not have run yet: the deadline itself binds.
    if record.expires_at and record.expires_at <= timezone.now():
        raise RecordError(
            "not_open",
            f"{record.record_number} expired and can no longer be signed.",
        )

    # What the signer saw must be what is on file. Guards against a page left
    # open across a void-and-reissue, and against a tampered client.
    if not content_hash or not hmac.compare_digest(
        str(content_hash), record.content_hash
    ):
        raise RecordError(
            "content_mismatch",
            "This is not the current version of the record. Reload and read "
            "it again.",
        )

    now = timezone.now()
    user_agent = (user_agent or "")[:400]

    if action == ACKNOWLEDGE:
        if signatory.status != SignatoryStatus.SIGNED:
            raise RecordError(
                "not_signed", "Only someone who has signed can acknowledge remarks."
            )
        owed = pending_acknowledgements(record).get(signatory.pk)
        if not owed:
            raise RecordError("nothing_to_acknowledge", "There are no new remarks.")
        signatory.remarks_acknowledged_at = now
        signatory.save(update_fields=["remarks_acknowledged_at", "updated_at"])
        log_event(
            record,
            RecordEventType.REMARKS_ACKNOWLEDGED,
            user=user,
            signatory=signatory,
            ip_address=ip_address,
            remarks_by=[r.name for r in owed],
        )
    else:
        if signatory.status != SignatoryStatus.PENDING:
            raise RecordError(
                "already_acted",
                f"{signatory.name} has already "
                f"{signatory.get_status_display().lower()}.",
            )
        signatory.method = method
        signatory.content_hash = record.content_hash
        signatory.ip_address = ip_address
        signatory.user_agent = user_agent

        if action == DECLINE:
            reason = (reason or "").strip()
            if not reason:
                raise RecordError(
                    "reason_required", "Please say why you are declining."
                )
            signatory.status = SignatoryStatus.DECLINED
            signatory.declined_at = now
            signatory.decline_reason = reason
            signatory.session_hash = ""
            signatory.session_expires_at = None
            signatory.save()
            # Only a required signatory's refusal closes the record. An
            # optional signatory's decline is on file; others still sign.
            if signatory.required:
                record.status = RecordStatus.DECLINED
                record.save(update_fields=["status", "updated_at"])
            log_event(
                record,
                RecordEventType.DECLINED,
                user=user,
                signatory=signatory,
                ip_address=ip_address,
                reason=reason,
            )
            return record

        typed_name = (typed_name or "").strip()
        remarks = (remarks or "").strip()
        if consent is not True:
            raise RecordError(
                "consent_required", "You must agree to sign electronically."
            )
        if len(typed_name) < 2:
            raise RecordError("name_required", "Type your full name to sign.")
        if action == SIGN_WITH_REMARKS and not remarks:
            raise RecordError("remarks_required", "Add your remarks, or sign without.")

        signatory.status = SignatoryStatus.SIGNED
        signatory.signed_at = now
        signatory.typed_name = typed_name[:255]
        signatory.remarks = remarks if action == SIGN_WITH_REMARKS else ""
        signatory.consent_version = CONSENT_VERSION
        signatory.save()
        log_event(
            record,
            RecordEventType.SIGNED,
            user=user,
            signatory=signatory,
            ip_address=ip_address,
            method=method,
            typed_name=signatory.typed_name,
            with_remarks=bool(signatory.remarks),
            consent_version=CONSENT_VERSION,
            content_hash=record.content_hash,
        )

    # A signing session is for one action. Spent here so a captured session
    # value cannot be replayed for a second.
    if signatory.session_hash:
        signatory.session_hash = ""
        signatory.session_expires_at = None
        signatory.save(update_fields=["session_hash", "session_expires_at"])

    if _is_complete(record):
        record.status = RecordStatus.COMPLETED
        record.completed_at = now
        record.save(update_fields=["status", "completed_at", "updated_at"])
        log_event(record, RecordEventType.COMPLETED)
        record.just_completed = True
    elif record.status != RecordStatus.PARTIALLY_SIGNED:
        record.status = RecordStatus.PARTIALLY_SIGNED
        record.save(update_fields=["status", "updated_at"])
    return record


@transaction.atomic
def expire_due(now=None) -> list[int]:
    """Expire every open record past its date. Returns their ids."""
    now = now or timezone.now()
    expired: list[int] = []
    for record in MeetingRecord.objects.select_for_update().filter(
        status__in=OPEN_STATUSES, expires_at__lt=now
    ):
        record.status = RecordStatus.EXPIRED
        record.save(update_fields=["status", "updated_at"])
        log_event(record, RecordEventType.EXPIRED)
        expired.append(record.pk)
    return expired
