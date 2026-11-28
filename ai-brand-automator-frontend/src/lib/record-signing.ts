/**
 * The signing page's client — for someone with no account.
 *
 * Deliberately not `apiClient`. That client attaches the logged-in user's
 * token and workspace, and redirects to the login page on a 401. A signer has
 * neither, and here a 401 means "confirm your email again", not "log in".
 * The emailed link is the credential, so these calls carry nothing else —
 * the same reasoning as the invitation page.
 */

import { env } from '@/lib/env';
import type { RecordDocument, RecordStatus } from '@/lib/meeting-records';

export interface SigningOverview {
  record_number: string;
  status: RecordStatus;
  agency: string;
  client: string;
  meeting_started_at: string | null;
  expires_at: string | null;
  signatory: {
    name: string;
    party_name: string;
    status: 'PENDING' | 'SIGNED' | 'DECLINED';
    /** Masked, e.g. `m•••a@example.com`. */
    email_hint: string;
  };
}

export interface OtherSignatory {
  id: number;
  party_name: string;
  name: string;
  title: string;
  required: boolean;
  status: 'PENDING' | 'SIGNED' | 'DECLINED';
  signed_at: string | null;
  remarks: string;
  decline_reason: string;
}

export interface SigningRecord extends SigningOverview {
  content_hash: string;
  document: RecordDocument;
  signatories: OtherSignatory[];
  consent: { version: string; text: string };
  can_sign: boolean;
  /** Names of people whose remarks this signer must still acknowledge. */
  remarks_to_acknowledge: string[];
}

export interface OpenedRecord extends SigningRecord {
  /** Held in memory only; never written to storage. */
  session: string;
}

export type SigningAction =
  | { action: 'sign'; typed_name: string; consent: boolean }
  | { action: 'sign_with_remarks'; typed_name: string; consent: boolean; remarks: string }
  | { action: 'decline'; reason: string }
  | { action: 'acknowledge_remarks' };

export class SigningError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'SigningError';
    this.code = code;
    this.status = status;
  }
}

function url(token: string, step = ''): string {
  return env.getApiUrl(
    `/onboarding/public/records/sign/${encodeURIComponent(token)}/${step}`,
  );
}

async function call<T>(input: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new SigningError(
      'network',
      'Could not reach the server. Check your connection and try again.',
      0,
    );
  }
  let body: { error?: string; detail?: string } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    /* No JSON body: reported from the status below. */
  }
  if (!response.ok) {
    throw new SigningError(
      body.error ?? `http_${response.status}`,
      body.detail ??
        (response.status === 429
          ? 'Too many attempts. Please wait a while and try again.'
          : 'Something went wrong. Please try again.'),
      response.status,
    );
  }
  return body as T;
}

export function getSigningOverview(token: string): Promise<SigningOverview> {
  return call<SigningOverview>(url(token));
}

export function requestSigningCode(token: string): Promise<{ sent_to: string }> {
  return call<{ sent_to: string }>(url(token, 'code/'), { method: 'POST', body: '{}' });
}

export function verifySigningCode(token: string, code: string): Promise<OpenedRecord> {
  return call<OpenedRecord>(url(token, 'verify/'), {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

export function submitSigning(
  token: string,
  session: string,
  contentHash: string,
  action: SigningAction,
): Promise<SigningRecord> {
  return call<SigningRecord>(url(token, 'submit/'), {
    method: 'POST',
    headers: { 'X-Signing-Session': session },
    body: JSON.stringify({ content_hash: contentHash, ...action }),
  });
}
