/**
 * Onboarding session API helpers (E-01).
 *
 * Named `onboarding-sessions` rather than `onboarding` because the original
 * `onboarding` app already owns companies, assets and wizard progress, and a
 * second module with the same name would be a coin flip every time someone
 * imports one. This wraps the `apps.onboarding` endpoints — Django label
 * `onboarding_sessions`, mounted at /api/v1/onboarding/ — which are the
 * meeting-driven half.
 *
 * Every call goes through apiClient, never raw fetch: it carries the JWT and
 * refreshes it, and a bare fetch would silently 401 the moment a token turned
 * over mid-session.
 */

import { apiClient } from '@/lib/api';

export function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/** §9.4's session states. */
export type SessionStatus =
  | 'DRAFT'
  | 'PREPARING'
  | 'READY'
  | 'MEETING_LIVE'
  | 'GATHERED'
  | 'PROCESSING'
  | 'REVIEW_PENDING'
  | 'CONFIRMED'
  | 'COMPLETED'
  | 'ESCALATED'
  | 'ARCHIVED';

export interface OnboardingSessionSummary {
  id: string;
  company: string | null;
  status: SessionStatus;
  questionnaire: string | null;
  created_at: string;
  updated_at: string;
}

/** Full session detail including process state (J-01). */
export interface SessionDetail extends OnboardingSessionSummary {
  legal_next_states: string[];
  evidence_manifest_hash: string;
  process_job_id: string;
  process_summary: Record<string, unknown>;
  consent: ConsentState;
  config?: Record<string, unknown>;
  is_key_delegate?: boolean;
}

/** Response from POST /sessions/{id}/process/ (J-01). */
export interface ProcessDispatchResponse {
  job_id: string;
  status: string;
  idempotent?: boolean;
  detail?: string;
}

/** §9.4's three workflows, as tagged on a question. */
export type WorkflowTarget = 'WF1' | 'WF2' | 'WF3';

export interface PreparedQuestion {
  id: string;
  order: number;
  text: string;
  origin: string;
  workflow_target: WorkflowTarget;
  target_field: string;
  /**
   * Server-authoritative checkbox state. OPEN is unchecked, GREEN is ticked.
   *
   * The C-05 card is explicit that this must not become client state: G-03
   * drives it from the agent's sufficiency signals during the meeting, and
   * "a component built around local state has to be rewritten".
   */
  status: 'OPEN' | 'GREEN' | 'SKIPPED';
}

export interface QuestionnaireDetail {
  id: string;
  session: string | null;
  status: 'DRAFT' | 'APPROVED' | 'SUPERSEDED';
  version: number;
  question_count: number;
  questions: PreparedQuestion[];
  coverage: Record<WorkflowTarget, number>;
}

export type MeetingStatus = 'SCHEDULED' | 'CANCELLED';

export type MeetingOrigin = 'APP' | 'GOOGLE';

export interface ScheduledMeeting {
  id: string;
  /**
   * Null for GOOGLE-origin entries.
   *
   * An event created in the operator's own calendar has no onboarding
   * session and never will, so the API serialises null. Typing this as
   * `string` invites an empty-string stand-in, which reads as a real id
   * everywhere it is passed.
   */
  session: string | null;
  company: string | null;
  title: string;
  /** UTC instant, ISO-8601. Rendered in the *viewer's* zone, never this one. */
  starts_at: string;
  ends_at: string;
  /**
   * The IANA zone the meeting was scheduled in.
   *
   * Carried for display — "09:00 in Europe/London" is what the operator
   * agreed with the brand owner, and a viewer in Sydney wants to know that as
   * well as their own 20:00. It is never used to compute an instant; the
   * instant is already in starts_at.
   */
  timezone: string;
  status: MeetingStatus;
  /** Where the entry came from. GOOGLE entries are mirrors of the operator's
   *  own calendar and this app is not their system of record (D-03, §11). */
  origin: MeetingOrigin;
  /**
   * Whether this app may edit the entry.
   *
   * Sent by the API rather than derived from `origin` here. The viewset
   * enforces the same rule server-side, and a rule written twice is a rule
   * that drifts — the second copy always outlives the reason for the first.
   */
  editable: boolean;
}

export interface MeetingRecordingSummary {
  id: string;
  session: string;
  status: string;
  duration_s: number | null;
  created_at: string;
}

/** Full recording row as returned by the library endpoint (I-01). */
export type RecordingStatus =
  | 'RECORDING'
  | 'UPLOADED'
  | 'TRANSCRIBED'
  | 'SUMMARIZED'
  | 'FAILED';

export interface RecordingItem {
  id: string;
  session: string;
  modality: string;
  status: RecordingStatus;
  duration_s: number | null;
  audio_asset: string | null;
  has_transcript: boolean;
  has_summary: boolean;
  started_at: string;
  stopped_at: string | null;
}

/** A clickable timestamp in a recording summary (I-02). */
export interface KeyMoment {
  t: number;
  label: string;
}

/** The LLM-generated summary for a recording (I-02). */
export interface RecordingSummary {
  text: string;
  key_moments: KeyMoment[];
}

/** Detail view of a single recording, including summary blob (I-02). */
export interface RecordingDetail extends RecordingItem {
  summary: RecordingSummary | null;
  playback_url?: string;
}

/** A single transcript segment (I-03). */
export interface TranscriptSegment {
  text: string;
  speaker: number;
  t_start: number;
  t_end: number;
  redaction_applied: boolean;
}

/** Response from GET /recordings/{id}/transcript/ (I-03). */
export interface TranscriptResponse {
  recording_id: string;
  duration_s: number | null;
  segments: TranscriptSegment[];
}

/**
 * Paths are relative to `/api/v1`, which `env.getApiUrl()` already prepends.
 *
 * Writing them in full produced `/api/v1/api/v1/onboarding/...` — every call
 * 404ing while the UI showed an ordinary empty list. `workspace.ts` sets the
 * same precedent with `const BASE = '/workspace'`.
 */
const BASE = '/onboarding';

/**
 * A page of results, or a bare array.
 *
 * DRF returns `{count, results}` when pagination is on and a plain array when
 * it is not, and this project configures it per-view. Handling both means a
 * pagination change in Django cannot turn a working list into an empty one
 * with no error.
 */
function itemsOf<T>(body: unknown): T[] {
  if (Array.isArray(body)) return body as T[];
  if (body && typeof body === 'object' && Array.isArray((body as { results?: unknown }).results)) {
    return (body as { results: T[] }).results;
  }
  return [];
}

/**
 * Read a list endpoint.
 *
 * `apiClient.get()` resolves to a `Response`, not to parsed JSON. Passing that
 * object straight into `itemsOf` matched none of its branches and returned an
 * empty array on every call, success or failure — the list looked empty rather
 * than broken. Throwing on a non-ok status is the other half: a 500 that
 * returns `[]` is indistinguishable from a tenant with no sessions.
 */
async function getList<T>(path: string): Promise<T[]> {
  const response = await apiClient.get(path);
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return itemsOf<T>(await response.json());
}

export async function listSessions(): Promise<OnboardingSessionSummary[]> {
  return getList<OnboardingSessionSummary>(`${BASE}/sessions/`);
}

export async function listRecordings(): Promise<MeetingRecordingSummary[]> {
  return getList<MeetingRecordingSummary>(`${BASE}/recordings/`);
}

/**
 * The deep link into wizard page 1 for a session's company.
 *
 * Carries both ids because the technical note requires it: K-01's review
 * links have to return the operator to where they were, and a wizard page
 * that does not know which session sent it there cannot do that.
 *
 * Built here rather than inline so the query shape lives in one place — the
 * wizard, the review links and any future caller have to agree on it.
 */
export function wizardDeepLink(
  session?: Pick<OnboardingSessionSummary, 'id' | 'company'> | null,
): string {
  if (!session) return '/onboarding/step-1';
  const params = new URLSearchParams();
  if (session.company) params.set('companyId', session.company);
  params.set('sessionId', session.id);
  return `/onboarding/step-1?${params.toString()}`;
}

/**
 * The approved questionnaire for a session, or null.
 *
 * Filtered server-side. Fetching every questionnaire and picking one in the
 * browser is correct only until the list paginates, and then it silently
 * shows nothing — the failure looks identical to "not approved yet".
 *
 * Null rather than throwing when there is none: an unapproved session is an
 * ordinary state with its own empty view (AC-2), not an error.
 */
export async function getApprovedQuestionnaire(
  sessionId: string,
): Promise<QuestionnaireDetail | null> {
  const rows = await getList<QuestionnaireDetail>(
    `${BASE}/questionnaires/?session=${encodeURIComponent(sessionId)}&status=APPROVED`,
  );
  // Highest version wins. Re-approval supersedes rather than replacing
  // (C-04 AC-3), so more than one approved row can exist over a session's
  // life and the newest is the one the operator just approved.
  return rows.sort((a, b) => b.version - a.version)[0] ?? null;
}

/** Meetings overlapping a window. The server narrows; see the D-01 viewset. */
export async function listMeetings(
  from: Date,
  to: Date,
): Promise<ScheduledMeeting[]> {
  const params = new URLSearchParams({
    from: from.toISOString(),
    to: to.toISOString(),
  });
  return getList<ScheduledMeeting>(`${BASE}/calendar/events/?${params.toString()}`);
}

async function sendMeeting(
  path: string,
  method: 'post' | 'patch',
  payload: unknown,
): Promise<ScheduledMeeting> {
  const response = await apiClient[method](path, payload);
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as ScheduledMeeting;
}

export interface MeetingDraft {
  session: string;
  title?: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
}

export async function createMeeting(draft: MeetingDraft): Promise<ScheduledMeeting> {
  return sendMeeting(`${BASE}/calendar/events/`, 'post', draft);
}

export async function updateMeeting(
  id: string,
  changes: Partial<MeetingDraft>,
): Promise<ScheduledMeeting> {
  return sendMeeting(`${BASE}/calendar/events/${id}/`, 'patch', changes);
}

export async function cancelMeeting(id: string): Promise<ScheduledMeeting> {
  // A POST, not a DELETE: cancelling releases the session and keeps the
  // record (D-01 AC-1), so the row survives and DELETE would misdescribe it.
  return sendMeeting(`${BASE}/calendar/events/${id}/cancel/`, 'post', {});
}

/**
 * The viewer's own IANA zone, from the browser.
 *
 * AC-2 wants "the same instant rendered in the viewer's local zone", and the
 * browser is the only thing that knows what that is. Falls back to UTC rather
 * than guessing an offset — a wrong zone name is recoverable, a fabricated
 * offset is the bug this story exists to avoid.
 */
export function viewerTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

// ── Consent (F-01) ───────────────────────────────────────────────────

/** §10.1's ConsentMethod, as B-07 shipped it. */
export type ConsentMethod = 'VERBAL_RECORDED' | 'CHECKBOX';

/**
 * What the session endpoint reports about consent.
 *
 * `granted` is false both when no consent was ever recorded and when it has
 * been revoked — B-07 reports only the *active* record, so a revoked one reads
 * as absent here. That is the right shape for this screen: both states mean
 * "the microphone stays shut", and the difference belongs in the audit trail
 * rather than in a banner.
 */
export interface ConsentState {
  granted: boolean;
  granted_at: string | null;
  method: ConsentMethod | null;
  scope: Record<string, boolean> | null;
}

export interface ConsentDraft {
  subject_name: string;
  method: ConsentMethod;
  scope: Record<string, boolean>;
}

/**
 * The scope every onboarding recording needs, and no more.
 *
 * Named here rather than assembled in the modal so the three things the
 * operator is asked to confirm are the three things actually sent. A scope
 * that drifts from the sentence above the button is consent for something
 * nobody agreed to.
 */
export const ONBOARDING_CONSENT_SCOPE: Record<string, boolean> = {
  audio: true,
  transcript: true,
  captured_media: true,
};

export async function getSessionConsent(sessionId: string): Promise<ConsentState> {
  const response = await apiClient.get(`${BASE}/sessions/${sessionId}/`);
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  const session = await response.json();
  return (
    session?.consent ?? {
      granted: false,
      granted_at: null,
      method: null,
      scope: null,
    }
  );
}

export async function grantConsent(
  sessionId: string,
  draft: ConsentDraft,
): Promise<ConsentState> {
  const response = await apiClient.post(
    `${BASE}/sessions/${sessionId}/consent/`,
    draft,
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  await response.json();
  // Re-read rather than trusting the write's echo: the session endpoint is
  // what the rest of this screen polls, and two sources for one fact is how
  // a banner and a button end up disagreeing.
  return getSessionConsent(sessionId);
}

// ── Recording lifecycle and upload (F-03) ────────────────────────────

export interface RecordingSession {
  recording_id: string;
  session_url: string;
  degraded_message: string;
}

/** Open a MeetingRecording row (B-08) and mint its upload session (F-03). */
export async function openRecording(sessionId: string): Promise<RecordingSession> {
  const opened = await apiClient.post(`${BASE}/sessions/${sessionId}/recordings/`, {
    modality: 'AUDIO',
  });
  if (!opened.ok) {
    throw new Error(`API ${opened.status}: ${await opened.text()}`);
  }
  const recording = await opened.json();

  const minted = await apiClient.post(
    `${BASE}/recordings/${recording.id}/upload-session/`,
    {},
  );
  if (!minted.ok) {
    throw new Error(`API ${minted.status}: ${await minted.text()}`);
  }
  const session = await minted.json();
  return {
    recording_id: String(recording.id),
    session_url: session.session_url,
    degraded_message: session.degraded_message,
  };
}

/**
 * Finalise a recording (AC-4).
 *
 * The Idempotency-Key is the recording id, which is stable across retries by
 * construction. A key derived from the attempt — a timestamp, a uuid per call
 * — would make every retry look like a new finalisation, which is the exact
 * duplicate the header exists to prevent.
 */
export async function finaliseRecording(
  recordingId: string,
  durationSeconds: number,
): Promise<void> {
  const response = await apiClient.post(`${BASE}/recordings/${recordingId}/stop/`, {
    duration_s: Math.round(durationSeconds),
    // In the body rather than a header: apiClient takes no custom headers and
    // this project forbids raw fetch. The server reads either, preferring the
    // header, so a client that can send one is unaffected.
    idempotency_key: `finalise-${recordingId}`,
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
}

// ── Media capture (H-01) ─────────────────────────────────────────────

export type UsageTag =
  | 'business_photo'
  | 'previous_ad'
  | 'brand_asset'
  | 'identity_document'
  | 'other';

export interface CapturedMedia {
  id: string;
  file_name: string;
  usage_tag: UsageTag;
  file_size: number;
  uploaded_at: string;
  file_type?: 'image' | 'video';
}

export async function uploadCapture(
  sessionId: string,
  file: File | Blob,
  usageTag: UsageTag,
): Promise<CapturedMedia> {
  const form = new FormData();
  form.append('file', file, file instanceof File ? file.name : 'capture.jpg');
  form.append('usage_tag', usageTag);

  const response = await apiClient.upload(
    `${BASE}/sessions/${sessionId}/media/`,
    form,
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as CapturedMedia;
}

// ── Recordings library (I-01) ─────────────────────────────────────────

/** List recordings for a session, newest first. */
export async function listSessionRecordings(
  sessionId: string,
): Promise<RecordingItem[]> {
  return getList<RecordingItem>(`${BASE}/sessions/${sessionId}/recordings/`);
}

/** List captured media for a session, newest first. */
export async function listSessionCaptures(
  sessionId: string,
): Promise<CapturedMedia[]> {
  return getList<CapturedMedia>(`${BASE}/sessions/${sessionId}/media/`);
}

/** Mint a short-lived signed URL for audio playback (§10.2). */
export async function getRecordingPlaybackUrl(
  recordingId: string,
): Promise<string | null> {
  const response = await apiClient.get(
    `${BASE}/recordings/${recordingId}/?include=signed_urls`,
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  const data = await response.json();
  return data.playback_url ?? null;
}

/** Fetch a single recording with its summary and signed playback URL (I-02). */
export async function getRecordingDetail(
  recordingId: string,
): Promise<RecordingDetail> {
  const response = await apiClient.get(
    `${BASE}/recordings/${recordingId}/?include=signed_urls`,
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  const data = (await response.json()) as RecordingDetail;
  if (
    data.summary &&
    typeof data.summary === 'object' &&
    Object.keys(data.summary).length === 0
  ) {
    data.summary = null;
  }
  return data;
}

/** Delete a recording (Admin+ only, §15). */
export async function deleteRecording(recordingId: string): Promise<void> {
  const response = await apiClient.delete(`${BASE}/recordings/${recordingId}/`);
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
}

/** Fetch transcript segments for a recording (I-03). */
export async function getRecordingTranscript(
  recordingId: string,
): Promise<TranscriptSegment[]> {
  const response = await apiClient.get(
    `${BASE}/recordings/${recordingId}/transcript/`,
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  const data = (await response.json()) as TranscriptResponse;
  return data.segments;
}

// ── Provenance (K-01) ───────────────────────────────────────────────

export interface ProvenanceSourceSpan {
  recording_id: string;
  t_start: number;
  t_end: number;
}

export type FieldClassification = 'KEY' | 'SECONDARY';

export type ProvenanceStatus = 'PENDING' | 'CONFIRMED' | 'EDITED' | 'CONFLICT';

export interface FieldProvenanceRow {
  id: number;
  session: number;
  model_name: string;
  field_name: string;
  extracted_value: unknown;
  final_value: unknown;
  classification: FieldClassification;
  confidence: number | null;
  source_recording: number | null;
  source_span: ProvenanceSourceSpan | null;
  source_media: number | null;
  status: ProvenanceStatus;
  reviewed_by: number | null;
  reviewed_at: string | null;
  wizard_page: number | null;
  wizard_page_label: string;
  created_at: string;
  updated_at: string;
}

export interface ProvenanceGroup {
  page: number | null;
  label: string;
  fields: FieldProvenanceRow[];
}

export interface ProvenanceResponse {
  session: number;
  groups: ProvenanceGroup[];
}

export interface ConflictSummaryItem {
  field_name: string;
  existing_status: string;
  new_confidence?: number;
  new_classification?: string;
}

export interface ProcessSummary {
  fields_written: number;
  key_count?: number;
  secondary_count?: number;
  conflicts: ConflictSummaryItem[];
  dropped_ungrounded: number;
  coverage: Record<string, number>;
  coverage_satisfied?: boolean;
  blocking_gaps?: string[];
  generated: string[];
}

export async function getSessionProvenance(
  sessionId: string,
): Promise<ProvenanceResponse> {
  const response = await apiClient.get(
    `${BASE}/sessions/${sessionId}/provenance/`,
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as ProvenanceResponse;
}

// ── Provenance review actions (K-02) ─────────────────────────────────

export async function confirmProvenance(
  rowId: number,
): Promise<FieldProvenanceRow> {
  const response = await apiClient.post(
    `${BASE}/provenance/${rowId}/confirm/`,
    {},
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as FieldProvenanceRow;
}

export async function editProvenance(
  rowId: number,
  finalValue: unknown,
): Promise<FieldProvenanceRow> {
  const response = await apiClient.post(
    `${BASE}/provenance/${rowId}/edit/`,
    { final_value: finalValue },
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as FieldProvenanceRow;
}

export async function submitReview(
  sessionId: string,
): Promise<SessionDetail> {
  const response = await apiClient.patch(
    `${BASE}/sessions/${sessionId}/`,
    { status: 'CONFIRMED' },
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as SessionDetail;
}

// ── Process dispatch (J-01) ──────────────────────────────────────────

/** Fetch full session detail including process state. */
export async function getSessionDetail(
  sessionId: string,
): Promise<SessionDetail> {
  const response = await apiClient.get(`${BASE}/sessions/${sessionId}/`);
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as SessionDetail;
}

/** Dispatch PROCESS for a session (J-01, §10.2.2). */
export async function triggerProcess(
  sessionId: string,
): Promise<ProcessDispatchResponse> {
  const response = await apiClient.post(
    `${BASE}/sessions/${sessionId}/process/`,
    {},
  );
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as ProcessDispatchResponse;
}
