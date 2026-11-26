/**
 * Signed meeting records — typed client.
 *
 * One record per recording: the meeting's agreements, description and clean
 * transcript, frozen and fingerprinted when it is issued. Every call goes
 * through `apiClient`; nothing here talks to the network on its own.
 */

import { apiClient } from '@/lib/api';

export type RecordStatus =
  | 'DRAFT'
  | 'ISSUED'
  | 'PARTIALLY_SIGNED'
  | 'COMPLETED'
  | 'DECLINED'
  | 'VOIDED'
  | 'EXPIRED';

export interface RecordSummary {
  id: number;
  record_number: string;
  version: number;
  status: RecordStatus;
  recording_id: number;
  session_id: number;
  content_hash: string;
  clause_version: string;
  issued_at: string | null;
  voided_at: string | null;
  void_reason: string;
  supersedes: number | null;
  created_at: string;
}

export interface MeetingWithRecord {
  recording_id: number;
  started_at: string | null;
  /** False until the recording has a description or clean transcript. */
  has_content: boolean;
  /** The latest version, or null when no record has been prepared. */
  record: RecordSummary | null;
  /** Earlier versions, oldest first. */
  history: RecordSummary[];
}

export interface ReadinessItem {
  code: string;
  ok: boolean;
  /** A blocking item stops the record being issued; a warning does not. */
  blocking: boolean;
  message: string;
  fields: string[];
}

export interface RecordDocument {
  record: { number: string; version: number; supersedes: string | null };
  clause: { version: string; text: string };
  parties: {
    agency: { name: string };
    client: {
      name: string;
      legal_name: string;
      registered_address: string;
      signatory_name: string;
      signatory_title: string;
      signatory_email: string;
      registration_number: string;
    };
  };
  meeting: {
    recording_id: number;
    started_at: string | null;
    stopped_at: string | null;
    duration_s: number | null;
  };
  attendees: { name: string; role: string }[];
  consent: { subject_name: string; method: string; granted_at: string | null } | null;
  completeness: { state: string; missing_s: number | null; note: string };
  agreements: { preamble: string; items: { number: string; text: string }[] };
  description: string;
  transcript: string[];
}

export interface RecordEvent {
  event_type: string;
  label: string;
  actor: string;
  occurred_at: string;
}

export interface RecordDetail extends RecordSummary {
  document: RecordDocument;
  events: RecordEvent[];
  /** Empty once the record has been issued. */
  readiness: ReadinessItem[];
}

/** A refusal from the server, with the reason it gave. */
export class RecordActionError extends Error {
  readonly code: string;
  readonly readiness: ReadinessItem[];

  constructor(code: string, message: string, readiness: ReadinessItem[] = []) {
    super(message);
    this.name = 'RecordActionError';
    this.code = code;
    this.readiness = readiness;
  }
}

const BASE = '/onboarding';

async function failure(response: Response): Promise<RecordActionError> {
  let body: { error?: string; detail?: string; readiness?: ReadinessItem[] } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    /* A response with no JSON body still needs reporting. */
  }
  return new RecordActionError(
    body.error ?? `http_${response.status}`,
    body.detail ?? `The request failed (HTTP ${response.status}).`,
    body.readiness ?? [],
  );
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw await failure(response);
  return (await response.json()) as T;
}

export async function listSessionRecords(
  sessionId: string,
): Promise<MeetingWithRecord[]> {
  const body = await json<{ meetings: MeetingWithRecord[] }>(
    await apiClient.get(`${BASE}/sessions/${sessionId}/records/`),
  );
  return body.meetings ?? [];
}

export async function getRecord(recordId: number): Promise<RecordDetail> {
  return json<RecordDetail>(await apiClient.get(`${BASE}/records/${recordId}/`));
}

export async function prepareRecord(recordingId: number): Promise<RecordDetail> {
  return json<RecordDetail>(
    await apiClient.post(`${BASE}/recordings/${recordingId}/records/`, {}),
  );
}

export async function issueRecord(
  recordId: number,
  acknowledgeIncomplete: boolean,
): Promise<RecordDetail> {
  return json<RecordDetail>(
    await apiClient.post(`${BASE}/records/${recordId}/issue/`, {
      acknowledge_incomplete: acknowledgeIncomplete,
    }),
  );
}

export async function voidRecord(
  recordId: number,
  reason: string,
): Promise<RecordDetail> {
  return json<RecordDetail>(
    await apiClient.post(`${BASE}/records/${recordId}/void/`, { reason }),
  );
}

export async function supersedeRecord(recordId: number): Promise<RecordDetail> {
  return json<RecordDetail>(
    await apiClient.post(`${BASE}/records/${recordId}/supersede/`, {}),
  );
}

export async function discardRecord(recordId: number): Promise<void> {
  const response = await apiClient.post(`${BASE}/records/${recordId}/discard/`, {});
  if (!response.ok) throw await failure(response);
}

/** Fetch a PDF and hand it to the browser as a download. */
async function download(endpoint: string, filename: string): Promise<void> {
  const response = await apiClient.get(endpoint);
  if (!response.ok) throw await failure(response);
  const url = URL.createObjectURL(await response.blob());
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function downloadRecordPdf(record: RecordSummary): Promise<void> {
  return download(`${BASE}/records/${record.id}/pdf/`, `${record.record_number}.pdf`);
}

export function downloadBinder(sessionId: string): Promise<void> {
  return download(
    `${BASE}/sessions/${sessionId}/binder/`,
    `meeting-records-session-${sessionId}.pdf`,
  );
}

export const STATUS_LABELS: Record<RecordStatus, string> = {
  DRAFT: 'Draft',
  ISSUED: 'Issued — awaiting signatures',
  PARTIALLY_SIGNED: 'Partially signed',
  COMPLETED: 'Signed',
  DECLINED: 'Declined',
  VOIDED: 'Voided',
  EXPIRED: 'Expired',
};

/** Statuses a newer version may replace. A signed record stands. */
export const SUPERSEDABLE: ReadonlySet<RecordStatus> = new Set([
  'DECLINED',
  'VOIDED',
  'EXPIRED',
]);
