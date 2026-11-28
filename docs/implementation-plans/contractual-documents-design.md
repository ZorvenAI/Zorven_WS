# Signed Meeting Records ("Contractual Documents") — Design Document

**Author:** Claude Code
**Date:** 2026-11-25
**Status:** Decisions D1–D8 accepted as recommended (2026-11-25). Implementation plan: [TICKET-ID-signed-meeting-records.md](TICKET-ID-signed-meeting-records.md)
**Scope:** Django backend (`apps.onboarding`), Next.js frontend, GCS, email. The OIA service changes only for the contractual questions added on 2026-11-25 (plan §5.5), which supersedes non-goal "Changes to how the OIA service generates T2 and T3" in spirit only: T2 and T3 generation is still untouched.

---

## 1. Problem Statement

An onboarding meeting between the agency (operator) and the client (participant)
produces commitments: budgets, timelines, scope, who does what. Today those live
in a description and a clean transcript that only the agency can see, that
nobody has confirmed, and that can still be overwritten.

The goal: whatever was discussed and agreed is written down, confirmed by both
parties with a signature, and kept in a form neither side can later change, so
there is no dispute tomorrow about what was said today.

## 2. What Already Exists

| Piece | State | Where |
|---|---|---|
| Per-meeting description (T3) with an `## Agreements` section | Done | `MeetingRecording.description` |
| Per-meeting clean transcript (T2) | Done | `MeetingRecording.transcript_clean` |
| Raw transcript (T1) and audio | Done | GCS |
| Meeting date/time, attendee names and roles | Done | `MeetingRecording.started_at`, `MeetingAttendee` |
| Consent to be recorded | Done | `ConsentRecord` |
| Transcript completeness (gaps in seconds) | Done | `transcript_complete`, `transcript_missing_s` |
| PDF library | Installed | `fpdf2` (used by the wizard PDF) |
| Private file storage with expiring links | Done | `files/services.py` `generate_signed_url` |
| Email sending | Configured, console backend by default | `settings.py` `EMAIL_*` |

So the *content* is roughly half done. Everything that makes it a signed record
is missing:

| Gap | Why it matters |
|---|---|
| No document entity | Nothing to sign, version, share or audit |
| Content is not frozen | `update_recording_summary` (`views.py:2982`) overwrites description and transcript unconditionally |
| Signers are unknown | `MeetingAttendee` holds a name and a role: no email, no account, no proof of identity |
| Agreements are free text | They cannot be numbered, referenced or individually disputed |
| No signing, no audit trail, no tamper evidence | |
| No client-facing access | The client has no way to read, sign or download anything |
| Erasure and retention would delete signed evidence | `erasure/` cascade covers transcripts |

## 3. Critique of the Requirement

These are the points where building the request literally would produce
something weaker than what is wanted.

**3.1 A signed transcript is a record, not a contract.** A contract needs
defined obligations, parties with authority, and usually term, payment,
governing law and dispute terms. A description plus a transcript has none of
those. Signing it creates strong *evidence of what was discussed and agreed*,
which is exactly the stated goal, but calling it "the contract" invites two
problems: a casual remark in a meeting could be argued to be binding, and it
could conflict with a real services agreement signed elsewhere. This design
therefore treats the document as a **Signed Meeting Record** with a stated legal
status clause (§5.3), and treats the numbered Agreements as the only operative
commitments.

**3.2 Software cannot make a document legally binding.** Enforceability depends
on jurisdiction, on the wording, and on facts outside the system. What the
system *can* do is satisfy the elements that electronic-signature laws commonly
look for: intent to sign, consent to sign electronically, attribution of the
signature to a person, an unaltered record, and a copy retained by each party.
The design delivers those (§12). The clause wording must be reviewed by a lawyer
before production use; that is a dependency, not something this feature closes.

**3.3 Both the description and the clean transcript are AI-generated.** The
description is a model's reading of the meeting; the clean transcript is a
model's rewrite of speech-to-text output. Asking people to sign AI text as fact
is the single biggest risk in the requirement. Mitigations in this design: a
stated order of precedence (audio, then raw transcript, then clean transcript,
then description), a mandatory review step before signing, and a way to record
a correction without editing the text (§3.5).

**3.4 Nobody's identity is established.** The client signer today would be a
typed name. That is trivially deniable. The minimum credible attribution is a
signing link sent to an email address the signer controls, plus a one-time code,
plus a recorded IP address, device and timestamp.

**3.5 "Never editable" collides with "the transcript got a number wrong."**
Speech-to-text mishears. If the text says 50 and the client said 15, the client
must be able to refuse or correct without anyone rewriting the record. Design:
signers can **sign**, **sign with remarks**, or **decline with a reason**.
Remarks are attributed, timestamped and printed in the document; the text itself
is never changed.

**3.6 Appending new meetings to an already-signed document breaks the
signature.** The request asks for each new recording to be added to the document
with its own date, time and signature section. If that is one growing file, then
every addition changes what earlier signers signed. Better: each meeting is its
own immutable signed record, and the session document is a **compiled binder**
of those records (§6). The reader sees exactly what was asked for, one document
with a dated, separately signed section per meeting, and the integrity holds.

**3.7 A shareable link to a full conversation is a data-exposure risk.** The
transcript contains everything said, including personal data. Sharing needs
expiry, revocation, an access log and optional passcode, not a permanent public
URL.

**3.8 Signed evidence conflicts with erasure and retention.** The platform
deletes transcripts on request and on a retention schedule. A signed record that
disappears is worthless; a signed record that can never be erased may breach
privacy law. This needs an explicit policy (§11, decision D7).

## 4. Goals and Non-Goals

**Goals**

1. One signed, immutable record per meeting, containing agreements, description and clean transcript.
2. One session-level document compiling every meeting's record, in date order, each with its own signature section.
3. Both parties sign electronically, with identity verification and a full audit trail.
4. Download as PDF; share through a controlled, revocable link.
5. Tamper evidence: anyone can verify a PDF matches what was signed.

**Non-goals (this feature)**

- Drafting a services agreement (terms, pricing, liability). Out of scope.
- A third-party e-signature provider. The design leaves a seam for one (§8.5).
- Certified or qualified signatures (government ID, notarisation).
- Editing transcript or description text. Never, per the standing rule.
- Changes to how the OIA service generates T2 and T3.

## 5. The Document

### 5.1 Terms

| Term | Meaning |
|---|---|
| **Meeting Record** | The signed document for one recording. Immutable once issued. |
| **Session Binder** | A generated PDF compiling all Meeting Records of one session. |
| **Signatory** | A named person who signs for a party. |
| **Issue** | The act of freezing content and sending it out for signature. |

### 5.2 Layout of a Meeting Record

1. **Cover**: title, both parties' names, meeting date, start and end time with time zone, record number and version, content fingerprint.
2. **Legal status and precedence** (§5.3).
3. **Attendance and recording consent**: from `MeetingAttendee` and `ConsentRecord`.
4. **Agreements**: numbered `A-1`, `A-2`, …; each with what was agreed, who proposed, who accepted, and the transcript timestamp. If the meeting has none, the section states "No agreements were recorded in this meeting."
5. **Description**: the remaining T3 sections, labelled as an AI-prepared summary.
6. **Clean transcript**: Annex A, line-numbered so remarks can cite lines.
7. **Completeness notice**: shown when the transcript has gaps, with the missing duration.
8. **Signer remarks**: any corrections or objections, attributed and timestamped.
9. **Signatures**: one block per signatory: name, role, party, email, signed-at time, method.
10. **Certificate of completion**: audit trail of every event, and the fingerprints.

### 5.3 Legal status clause (draft wording, for legal review)

> This document records a meeting between the parties named above. By signing,
> each party confirms that the numbered Agreements accurately state what the
> parties agreed in this meeting. The Description is a summary prepared with
> automated tools and the Transcript is an automated transcription; they are
> included as supporting record. If they differ, the audio recording prevails,
> then the raw transcript, then the clean transcript, then the Description.
> This document does not replace any signed services agreement between the
> parties; where the two conflict, [the services agreement prevails / the later
> document prevails — decision D1].

### 5.4 Numbering agreements without rewording them

The `## Agreements` section is already stored as bullets in the description. At
issue time the bullets are split out **deterministically** (text parsing, no
model call) into numbered items. The words are untouched, which keeps the "never
reworded once written" rule intact. The remaining description sections follow
unchanged.

## 6. Multiple Meetings in One Session

- Each recording gets its own Meeting Record, issued and signed independently.
- The Session Binder is generated on demand: cover page, index of meetings by
  date and time with each record's status, then every Meeting Record in order
  with its own signature section, then a manifest listing each record's
  fingerprint.
- Adding a third meeting never touches the first two records. The binder is
  simply regenerated and now has three sections.
- The binder shows unsigned or pending records clearly marked as such, so it is
  never mistaken for fully executed when it is not.
- A separate sign-off on the binder as a whole is possible later but is not
  proposed now: it would duplicate the per-meeting signatures.

## 7. Lifecycle

```
          issue                 first signature            last signature
DRAFT ───────────► ISSUED ───────────────► PARTIALLY_SIGNED ───────────► COMPLETED
  │                  │ │                          │
  │                  │ └── decline ──► DECLINED   └── decline ──► DECLINED
  │                  └── expiry ───► EXPIRED
  └── (discard)      any non-completed state ── void ──► VOIDED
```

- **DRAFT**: agency previews the document, adds signatories. Content still follows the recording.
- **ISSUED**: content is frozen into a snapshot and fingerprinted. From here the record never changes.
- **Sign with remarks**: if a remark is added after another party has signed, that party is notified and must acknowledge it before the record reaches COMPLETED.
- **DECLINED / VOIDED / EXPIRED**: terminal. A corrected record is issued as a new version that names the one it supersedes. Old versions are kept.
- A COMPLETED record cannot be voided, edited or superseded. A later meeting can record a changed agreement; that is a new record.

## 8. Signing

### 8.1 Who signs

One authorised signatory per party is required; additional signatories are
optional. The agency user adds them in DRAFT: name, email, party, title. Names
are pre-filled from `MeetingAttendee`; emails must be entered, since none are
stored today.

### 8.2 The client's signing ceremony (no account needed)

1. Signatory receives an email with a single-use, expiring link.
2. Opening it requests a six-digit code sent to the same address.
3. They read the full record in the browser.
4. They tick consent to sign electronically, then choose Sign, Sign with remarks, or Decline.
5. They type their full name as their signature.
6. They, and every other party, receive the PDF by email once the record is completed.

### 8.3 The agency's signing

Same screen, reached while logged in. The login replaces the email code; the
user must still tick consent and type their name.

### 8.4 What is recorded per signature

Signatory identity and email, verified-email proof (code issued and matched
times), consent text version, typed name, action, remarks, server timestamp in
UTC, IP address, browser details, and the content fingerprint that was on screen.

### 8.5 Build versus provider

Recommended: build the ceremony above in-house now, behind a small signing
interface so a provider such as DocuSign or Dropbox Sign can be plugged in
later without changing the document model. In-house is cheaper and keeps
transcripts inside the platform; a provider gives a better-known evidentiary
trail and is the stronger choice if these records will back high-value deals.

## 9. Integrity

- **Content fingerprint**: at issue, the frozen content (parties, meeting
  metadata, agreements, description, transcript, clause text) is serialised in
  a canonical form and hashed with SHA-256. Signatures bind to this fingerprint,
  so a later signature does not invalidate an earlier one.
- **PDF fingerprint**: the final PDF's SHA-256 is stored and printed in the
  certificate.
- **Verification**: a page where anyone can upload a PDF, or enter a record
  number, and see whether it matches what was signed.
- **Storage**: snapshot and final PDF are written once to GCS; the bucket
  should use object retention so even an administrator cannot overwrite them.
- **Append-only audit trail**: events are inserted, never updated or deleted.
- **Optional hardening (phase 2)**: a cryptographic seal embedded in the PDF
  with a platform certificate, so standard PDF readers show "not modified since
  signing". Needs a signing key in Secret Manager; library choice to be
  verified in the implementation plan.
- **Source freeze**: once any record for a recording is issued,
  `update_recording_summary` and the process callback must refuse to change that
  recording's description and transcript.

## 10. Data Model (Django, app label `onboarding_sessions`)

All models carry `tenant`, `created_at`, `updated_at` per project convention.

**`MeetingRecord`**: `session` FK, `recording` FK, `record_number` (human
readable, unique per tenant), `version`, `supersedes` (self FK, nullable),
`status`, `snapshot` (JSON, set at issue), `content_hash`, `clause_version`,
`issued_at`, `issued_by`, `expires_at`, `completed_at`, `pdf_gcs_path`,
`pdf_hash`, `legal_hold` (bool). Constraint: at most one non-terminal record per
recording.

**`RecordSignatory`**: `record` FK, `party` (AGENCY / CLIENT), `name`, `email`,
`title`, `user` FK (nullable, for agency users), `required` (bool),
`signing_order`, `status` (PENDING / SIGNED / DECLINED), `token_hash`,
`token_expires_at`, `signed_at`, `typed_name`, `remarks`, `decline_reason`,
`ip_address`, `user_agent`, `consent_version`. Signing tokens are stored hashed,
never in plain text.

**`RecordEvent`**: `record` FK, `signatory` FK (nullable), `actor_user` FK
(nullable), `event_type` (CREATED, ISSUED, EMAIL_SENT, VIEWED, CODE_SENT,
CODE_VERIFIED, SIGNED, REMARK_ADDED, REMARK_ACKNOWLEDGED, DECLINED, VOIDED,
EXPIRED, COMPLETED, DOWNLOADED, SHARED, SHARE_REVOKED, SHARE_ACCESSED),
`detail` (JSON), `ip_address`, `occurred_at`. Insert-only.

**`RecordShare`**: `record` FK (nullable) or `session` FK (for a binder),
`token_hash`, `created_by`, `recipient_email` (optional), `passcode_hash`
(optional), `expires_at`, `revoked_at`, `access_count`, `last_accessed_at`.

## 11. Sharing, Download, Retention

- **Download**: PDF for a single record or for the session binder, through a
  short-lived signed storage link. Every download is logged.
- **Share**: agency creates a link with an expiry (default 14 days), optional
  passcode and optional named recipient; can revoke at any time. Viewers see a
  read-only page and can download. Every access is logged.
- **Before completion**, downloads carry a visible "NOT FULLY SIGNED" watermark.
- **Retention**: a record with `legal_hold` is excluded from the retention
  sweep and the erasure cascade; an erasure request touching it is logged as
  held, with the reason. Hold duration is a tenant setting (decision D7).

## 12. How the Design Maps to What E-Signature Laws Look For

| Element | How it is met |
|---|---|
| Intent to sign | Explicit Sign action plus typed name |
| Consent to sign electronically | Mandatory tick box; consent text version stored |
| Attribution | Emailed single-use link, one-time code, IP, device, timestamp |
| Integrity of the record | Frozen snapshot, SHA-256 fingerprints, write-once storage, verification page |
| Retention and access | Every party is emailed the final PDF; download remains available |
| Audit trail | Append-only events printed in the certificate |

This raises the evidentiary quality of the record. It is not a legal opinion,
and jurisdiction-specific rules still need a lawyer's review (decision D4).

## 13. API and Screens

**Authenticated (agency)**, under `/api/v1/onboarding/`:

| Method and path | Purpose |
|---|---|
| `GET sessions/<pk>/records/` | List records for a session |
| `POST recordings/<pk>/records/` | Create a DRAFT record |
| `GET records/<pk>/` | Detail, including signatories and events |
| `PUT records/<pk>/signatories/` | Set signatories (DRAFT only) |
| `POST records/<pk>/issue/` | Freeze and send for signature |
| `POST records/<pk>/sign/` | Agency signatory signs |
| `POST records/<pk>/void/` | Void with reason |
| `POST records/<pk>/remind/` | Resend to pending signatories |
| `GET records/<pk>/pdf/` | Download link |
| `GET sessions/<pk>/binder/` | Session binder download link |
| `POST records/<pk>/shares/`, `DELETE shares/<pk>/` | Create and revoke share links |

**Public (token-authenticated, rate-limited)**:

| Method and path | Purpose |
|---|---|
| `GET public/records/sign/<token>/` | Record metadata, masked email |
| `POST …/sign/<token>/code/` | Send one-time code |
| `POST …/sign/<token>/verify/` | Verify code, return the record |
| `POST …/sign/<token>/submit/` | Sign, sign with remarks, or decline |
| `GET public/records/shared/<token>/` | Read-only shared view |
| `POST public/records/verify/` | Check a PDF or fingerprint |

**Screens**

- A new **Documents** tab on the onboarding session: one row per meeting with
  date, time, status and signatories; actions Prepare, Issue, Sign, Remind,
  Download, Share, Void; a Download Binder button.
- **Prepare** view: live preview, signatory editor, completeness warnings.
- Public **signing page** and **shared view page**, outside the logged-in app.
- Public **verification page**.

## 14. Security, Deployment, Risks

**Security**
- Tokens: 256-bit random, stored hashed, single-purpose, expiring.
- One-time codes: short-lived, limited attempts, rate-limited per token and IP.
- Public pages expose only the one record the token is for; tenant isolation is by token, never by a client-supplied ID.
- PDFs are never public objects; access is always through a logged, expiring link.
- Public endpoints need a gateway route without login. Kong configuration is on the do-not-modify list, so this needs team coordination; to be confirmed in the implementation plan.

**Deployment**
- One migration (four tables). No new service.
- Production needs a real outbound email provider; the default backend only prints to the console.
- GCS bucket retention policy for signed records.
- Frontend: two public routes that skip the login guard.

**Risks**

| Risk | Mitigation |
|---|---|
| AI text signed as fact | Precedence clause, mandatory review, remarks, decline |
| Wrong person signs | Email code; authorised-signatory attestation at signing |
| Email lands in spam | Reminders, copyable link for the agency to send manually |
| Clause wording unenforceable | Lawyer review before production; clause is versioned |
| Existing recordings have mixed transcripts | Completeness notice; agency reviews before issuing |
| Erasure versus evidence | Legal hold with a defined duration |

## 15. Decisions Needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | Is the record itself binding, or evidence alongside a separate services agreement? Which prevails on conflict? | Signed record; numbered Agreements are confirmed commitments; a signed services agreement prevails |
| D2 | Who must sign? | One authorised signatory per party; others optional |
| D3 | Does the client need a Zorven account to sign? | No. Email link plus one-time code |
| D4 | Which jurisdictions must this hold up in? | Needed to brief the lawyer; does not change the architecture |
| D5 | Build signing in-house or use a provider? | In-house now, provider-ready interface |
| D6 | How are transcription errors handled? | Sign with remarks or decline; text never edited |
| D7 | Signed records versus erasure and retention | Legal hold on issued records for a tenant-set period (suggest 7 years), erasure requests logged as held |
| D8 | Who may share, and with whom? | Agency admins and editors; expiring, revocable links; client may forward their own copy |

## 16. Assumptions

1. The agency is the tenant; the client is the tenant's single `Company`.
2. The document is generated in Django; the OIA service is unchanged.
3. English only for clause text in the first release.
4. Agreements stay as stored text; numbering is derived, not regenerated.
5. Existing recordings (including recording 85) can be issued as records once signatories are added.
6. The embedded PDF seal is phase 2; phase 1 relies on fingerprints and write-once storage.

## 17. Suggested Phasing

1. **Phase 1 — Record and PDF**: model, snapshot and freeze, agreement numbering, PDF, Documents tab, download, binder.
2. **Phase 2 — Signing**: signatories, email link and code, signing page, audit trail, certificate, completion emails.
3. **Phase 3 — Sharing and verification**: share links, verification page, legal hold in erasure and retention.
4. **Phase 4 — Hardening**: embedded PDF seal, optional provider adapter.

Each phase is independently shippable; phases 1 and 2 together meet the stated
requirement.
