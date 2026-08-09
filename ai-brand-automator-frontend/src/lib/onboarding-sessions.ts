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

export interface MeetingRecordingSummary {
  id: string;
  session: string;
  status: string;
  duration_s: number | null;
  created_at: string;
}

/**
 * A page of results, or a bare array.
 *
 * DRF returns `{count, results}` when pagination is on and a plain array when
 * it is not, and this project configures it per-view. Handling both here means
 * a pagination change in Django cannot turn a working list into an empty one
 * with no error.
 */
function itemsOf<T>(body: unknown): T[] {
  if (Array.isArray(body)) return body as T[];
  if (body && typeof body === 'object' && Array.isArray((body as { results?: unknown }).results)) {
    return (body as { results: T[] }).results;
  }
  return [];
}

export async function listSessions(): Promise<OnboardingSessionSummary[]> {
  return itemsOf<OnboardingSessionSummary>(
    await apiClient.get('/api/v1/onboarding/sessions/'),
  );
}

export async function listRecordings(): Promise<MeetingRecordingSummary[]> {
  return itemsOf<MeetingRecordingSummary>(
    await apiClient.get('/api/v1/onboarding/recordings/'),
  );
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
