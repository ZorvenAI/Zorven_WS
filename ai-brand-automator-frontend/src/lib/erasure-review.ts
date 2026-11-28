/**
 * Erasure review queue: GDPR erasure requests held because the person's
 * sessions contain signed meeting records. An owner or admin keeps them under
 * legal hold or erases them anyway; both need a reason and are final.
 */

import { apiClient } from '@/lib/api';

const BASE = '/onboarding/erasure/review';
const RETENTION = '/onboarding/retention/';

export const MIN_REASON_CHARS = 10;

export type ReviewStatus = 'PENDING' | 'KEPT' | 'ERASED';

export interface HeldRecord {
  record_number: string;
  status: string;
}

export interface HeldSession {
  session_id: string;
  company_name: string;
  records: HeldRecord[];
}

export interface ErasedRecord {
  record_number: string;
  status: string;
  content_hash: string;
  issued_at: string | null;
  completed_at: string | null;
}

export interface ErasureReviewItem {
  id: number;
  subject_name: string;
  reason: string;
  requested_at: string;
  requested_by: string | null;
  days_waiting: number;
  overdue: boolean;
  held: HeldSession[];
  review_status: ReviewStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_reason: string;
  hold_until: string | null;
  erase_in_progress: boolean;
  last_error: string;
  erased_signed_records: ErasedRecord[];
  default_hold_until: string;
}

/** A refused decision, carrying the server's own explanation. */
export class ReviewActionError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = 'ReviewActionError';
    this.code = code;
    this.status = status;
  }
}

async function failure(response: Response): Promise<ReviewActionError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const record = (body && typeof body === 'object' ? body : {}) as Record<string, unknown>;
  const detail = typeof record.detail === 'string' ? record.detail : '';
  const code = typeof record.error === 'string' ? record.error : `http_${response.status}`;
  return new ReviewActionError(
    detail || `The request failed (${response.status}).`,
    code,
    response.status,
  );
}

export async function listErasureReviews(
  status: ReviewStatus = 'PENDING',
): Promise<ErasureReviewItem[]> {
  const query = status === 'PENDING' ? '' : `?status=${status}`;
  const response = await apiClient.get(`${BASE}/${query}`);
  if (!response.ok) throw await failure(response);
  return (await response.json()) as ErasureReviewItem[];
}

export async function keepUnderHold(
  id: number,
  reason: string,
  holdUntil?: string,
): Promise<ErasureReviewItem> {
  const body: Record<string, string> = { reason };
  if (holdUntil) body.hold_until = holdUntil;
  const response = await apiClient.post(`${BASE}/${id}/keep/`, body);
  if (!response.ok) throw await failure(response);
  return (await response.json()) as ErasureReviewItem;
}

export async function eraseAnyway(
  id: number,
  reason: string,
  confirmSubject: string,
): Promise<ErasureReviewItem> {
  const response = await apiClient.post(`${BASE}/${id}/erase/`, {
    reason,
    confirm_subject: confirmSubject,
  });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as ErasureReviewItem;
}

export async function getLegalHoldYears(): Promise<number> {
  const response = await apiClient.get(RETENTION);
  if (!response.ok) throw await failure(response);
  const body = (await response.json()) as { legal_hold_years?: number };
  return body.legal_hold_years ?? 7;
}

export async function setLegalHoldYears(years: number): Promise<number> {
  const response = await apiClient.patch(RETENTION, { legal_hold_years: years });
  if (!response.ok) throw await failure(response);
  const body = (await response.json()) as { legal_hold_years: number };
  return body.legal_hold_years;
}
