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

/** §9.4's session states. */
export type SessionStatus =
  | 'DRAFT'
  | 'PREPARING'
  | 'READY'
  | 'MEETING_LIVE'
  | 'PROCESSING'
  | 'REVIEW'
  | 'COMPLETE'
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

export interface MeetingRecordingSummary {
  id: string;
  session: string;
  status: string;
  duration_s: number | null;
  created_at: string;
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
