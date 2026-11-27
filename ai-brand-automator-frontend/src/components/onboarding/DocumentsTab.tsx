'use client';

/**
 * Documents tab — the signed record of each meeting in a session.
 *
 * One row per meeting. A meeting with a description or transcript can be
 * prepared as a draft record, checked, and issued; issuing freezes the content
 * for good, so it is a two-step action here with the consequence spelled out.
 *
 * Nothing in this component decides whether a record may be issued. The
 * server's readiness list does, and this renders it — a check that lived in
 * both places would eventually disagree with itself.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSignature,
  Loader2,
  RefreshCw,
  XCircle,
} from 'lucide-react';

import { useTenantRole } from '@/hooks/useTenantRole';
import {
  RecordActionError,
  STATUS_LABELS,
  SUPERSEDABLE,
  discardRecord,
  downloadBinder,
  downloadRecordPdf,
  getRecord,
  issueRecord,
  listSessionRecords,
  prepareRecord,
  supersedeRecord,
  voidRecord,
  type MeetingWithRecord,
  type ReadinessItem,
  type RecordDetail,
  type RecordStatus,
} from '@/lib/meeting-records';

export interface DocumentsTabProps {
  sessionId: string;
}

const STATUS_STYLES: Record<RecordStatus, string> = {
  DRAFT: 'border-white/20 text-brand-silver',
  ISSUED: 'border-amber-300/40 text-amber-200',
  PARTIALLY_SIGNED: 'border-amber-300/40 text-amber-200',
  COMPLETED: 'border-emerald-300/40 text-emerald-200',
  DECLINED: 'border-rose-300/40 text-rose-200',
  VOIDED: 'border-rose-300/40 text-rose-200',
  EXPIRED: 'border-rose-300/40 text-rose-200',
};

function formatWhen(iso: string | null): string {
  if (!iso) return 'Time not recorded';
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.';
}

function Bold({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*.+?\*\*)/g).map((part, index) =>
        part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
          <strong key={index} className="text-white">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}

function Readiness({ items }: { items: ReadinessItem[] }) {
  return (
    <ul className="space-y-1.5" aria-label="Readiness checks">
      {items.map((item) => (
        <li key={item.code} className="flex items-start gap-2 text-sm">
          {item.ok ? (
            <CheckCircle2
              className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300"
              aria-label="Passed"
            />
          ) : item.blocking ? (
            <XCircle
              className="mt-0.5 h-4 w-4 shrink-0 text-rose-300"
              aria-label="Must be fixed"
            />
          ) : (
            <AlertTriangle
              className="mt-0.5 h-4 w-4 shrink-0 text-amber-300"
              aria-label="Note"
            />
          )}
          <span className={item.ok ? 'text-brand-silver' : 'text-white'}>
            {item.message}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Preview({ detail }: { detail: RecordDetail }) {
  const doc = detail.document;
  const client = doc.parties.client;
  return (
    <div className="space-y-5 text-sm text-brand-silver">
      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-white/60">
          Parties
        </h4>
        <p>
          <span className="text-white">{doc.parties.agency.name || '—'}</span> and{' '}
          <span className="text-white">{client.legal_name || client.name || '—'}</span>
        </p>
        <p>
          Signing for the client: {client.signatory_name || '—'}
          {client.signatory_title ? `, ${client.signatory_title}` : ''}
          {client.signatory_email ? ` (${client.signatory_email})` : ''}
        </p>
      </section>

      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-white/60">
          Agreements
        </h4>
        {doc.agreements.items.length === 0 ? (
          <p>No agreements were recorded in this meeting.</p>
        ) : (
          <ol className="space-y-1.5" aria-label="Agreements">
            {doc.agreements.items.map((item) => (
              <li key={item.number} className="flex gap-3">
                <span className="shrink-0 font-semibold text-white">{item.number}</span>
                <span className="whitespace-pre-line">
                  <Bold text={item.text} />
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-white/60">
          Clean transcript ({doc.transcript.length} lines)
        </h4>
        {doc.transcript.length === 0 ? (
          <p>No clean transcript is available for this meeting.</p>
        ) : (
          <ol
            className="max-h-72 space-y-1 overflow-y-auto rounded-lg bg-white/5 p-3"
            aria-label="Transcript"
          >
            {doc.transcript.map((line, index) => (
              <li key={index} className="flex gap-3">
                <span className="w-7 shrink-0 text-right text-xs text-white/40">
                  {index + 1}
                </span>
                <span className="break-words">{line}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <p className="text-xs">
        The PDF also carries the description, attendance, recording consent and
        the legal status clause.
      </p>
    </div>
  );
}

export default function DocumentsTab({ sessionId }: DocumentsTabProps) {
  const { canEdit } = useTenantRole();
  const [meetings, setMeetings] = useState<MeetingWithRecord[]>([]);
  const [detail, setDetail] = useState<RecordDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingIssue, setConfirmingIssue] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [voiding, setVoiding] = useState(false);
  const [voidReason, setVoidReason] = useState('');

  const resetActions = () => {
    setConfirmingIssue(false);
    setAcknowledged(false);
    setVoiding(false);
    setVoidReason('');
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMeetings(await listSessionRecords(sessionId));
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Run one action, then show whatever record it produced and refresh rows.
   *
   * Only an action that changes a record closes the open forms: downloading a
   * PDF to check the wording must not throw away a void reason being typed.
   */
  const run = async (
    action: () => Promise<RecordDetail | null | void>,
    { changes = false }: { changes?: boolean } = {},
  ) => {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      if (result !== undefined) setDetail(result);
      if (changes) resetActions();
      setMeetings(await listSessionRecords(sessionId));
    } catch (err: unknown) {
      // A refused issue comes back with the checks that failed; show them in
      // place of the stale ones rather than only a sentence about it.
      if (err instanceof RecordActionError && err.readiness.length > 0 && detail) {
        setDetail({ ...detail, readiness: err.readiness });
      }
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-brand-silver" />
      </div>
    );
  }

  const blocking = (detail?.readiness ?? []).filter((i) => i.blocking && !i.ok);
  // The one blocker the operator clears here rather than elsewhere: an
  // incomplete transcript, issued knowingly.
  const needsAcknowledgement = blocking.some((i) => i.code === 'completeness');
  const otherBlockers = blocking.filter((i) => i.code !== 'completeness');
  const hasAnyRecord = meetings.some((m) => m.record !== null);

  return (
    <div className="space-y-5 p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Meeting records</h2>
          <p className="text-sm text-brand-silver">
            The record of each meeting, for both parties to sign.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 rounded border border-white/10 px-2.5 py-1 text-xs text-brand-silver transition-colors hover:bg-white/5 hover:text-white"
          >
            <RefreshCw className="h-3 w-3" aria-hidden />
            Refresh
          </button>
          <button
            type="button"
            disabled={!hasAnyRecord || busy}
            onClick={() => void run(() => downloadBinder(sessionId))}
            className="inline-flex items-center gap-1.5 rounded border border-white/10 px-2.5 py-1 text-xs text-brand-silver transition-colors hover:bg-white/5 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Download className="h-3 w-3" aria-hidden />
            Download all meetings
          </button>
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-rose-300/30 p-3 text-sm text-rose-200"
        >
          {error}
        </p>
      )}

      {meetings.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-12 text-brand-silver">
          <FileSignature className="h-10 w-10 opacity-30" aria-hidden />
          <p className="text-sm">No meetings have been recorded in this session yet.</p>
        </div>
      ) : (
        <ul className="space-y-2" aria-label="Meetings">
          {meetings.map((meeting, index) => {
            const record = meeting.record;
            const open = record !== null && detail?.id === record.id;
            return (
              <li
                key={meeting.recording_id}
                className={`glass-card flex flex-wrap items-center justify-between gap-3 p-4 ${
                  open ? 'border border-brand-electric/60' : ''
                }`}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white">
                    Meeting {index + 1}
                    <span className="ml-2 font-normal text-brand-silver">
                      {formatWhen(meeting.started_at)}
                    </span>
                  </p>
                  {record ? (
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-brand-silver">
                      <span>{record.record_number}</span>
                      <span
                        className={`rounded border px-1.5 py-0.5 ${STATUS_STYLES[record.status]}`}
                      >
                        {STATUS_LABELS[record.status]}
                      </span>
                      {meeting.history.length > 0 && (
                        <span>
                          {meeting.history.length} earlier version
                          {meeting.history.length === 1 ? '' : 's'}
                        </span>
                      )}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-brand-silver">
                      {meeting.has_content
                        ? 'No record prepared yet.'
                        : 'Process this recording before preparing a record.'}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {record ? (
                    <>
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={`Open ${record.record_number}`}
                        onClick={() => void run(() => getRecord(record.id))}
                        className="rounded border border-white/10 px-3 py-1.5 text-xs text-white transition-colors hover:bg-white/5 disabled:opacity-40"
                      >
                        {open ? 'Reload' : 'Open'}
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={`Download ${record.record_number}`}
                        onClick={() => void run(() => downloadRecordPdf(record))}
                        className="inline-flex items-center gap-1.5 rounded border border-white/10 px-3 py-1.5 text-xs text-white transition-colors hover:bg-white/5 disabled:opacity-40"
                      >
                        <Download className="h-3 w-3" aria-hidden />
                        PDF
                      </button>
                    </>
                  ) : (
                    canEdit && (
                      <button
                        type="button"
                        disabled={!meeting.has_content || busy}
                        onClick={() =>
                          void run(() => prepareRecord(meeting.recording_id), { changes: true })
                        }
                        className="btn-primary text-xs disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Prepare record
                      </button>
                    )
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {detail && (
        <section
          aria-label={`Record ${detail.record_number}`}
          className="glass-card space-y-5 p-5"
        >
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-white">
              {detail.record_number}
              <span
                className={`ml-2 rounded border px-1.5 py-0.5 text-xs font-normal ${STATUS_STYLES[detail.status]}`}
              >
                {STATUS_LABELS[detail.status]}
              </span>
            </h3>
            {detail.content_hash ? (
              <p className="mt-1 break-all text-xs text-brand-silver">
                Fingerprint{' '}
                <span data-testid="fingerprint" className="font-mono">
                  {detail.content_hash}
                </span>
              </p>
            ) : (
              <p className="mt-1 text-xs text-brand-silver">
                Not issued. This draft follows the recording until you issue it.
              </p>
            )}
            {detail.status === 'VOIDED' && detail.void_reason && (
              <p className="mt-1 text-xs text-rose-200">Voided: {detail.void_reason}</p>
            )}
          </div>

          {detail.status === 'DRAFT' && <Readiness items={detail.readiness} />}

          {canEdit && detail.status === 'DRAFT' && (
            <div className="space-y-3 rounded-lg border border-white/10 p-4">
              {!confirmingIssue ? (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={busy || otherBlockers.length > 0}
                    onClick={() => setConfirmingIssue(true)}
                    className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Issue record…
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void run(
                        async () => {
                          await discardRecord(detail.id);
                          return null;
                        },
                        { changes: true },
                      )
                    }
                    className="rounded border border-white/10 px-3 py-1.5 text-sm text-brand-silver transition-colors hover:bg-white/5 hover:text-white disabled:opacity-40"
                  >
                    Discard draft
                  </button>
                  {otherBlockers.length > 0 && (
                    <span className="text-xs text-brand-silver">
                      Fix the items marked above before issuing.
                    </span>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-white">
                    Issuing freezes this record permanently. Its agreements,
                    description and transcript can never be changed afterwards,
                    and neither can the recording they came from.
                  </p>
                  {needsAcknowledgement && (
                    <label className="flex items-start gap-2 text-sm text-brand-silver">
                      <input
                        type="checkbox"
                        checked={acknowledged}
                        onChange={(e) => setAcknowledged(e.target.checked)}
                        className="mt-1 h-4 w-4 shrink-0"
                      />
                      I understand the transcript does not cover the whole meeting,
                      and that the record will say so.
                    </label>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={busy || (needsAcknowledgement && !acknowledged)}
                      onClick={() =>
                        void run(() => issueRecord(detail.id, acknowledged), { changes: true })
                      }
                      className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Issue and freeze
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={resetActions}
                      className="rounded border border-white/10 px-3 py-1.5 text-sm text-brand-silver transition-colors hover:bg-white/5 hover:text-white"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {canEdit &&
            (detail.status === 'ISSUED' || detail.status === 'PARTIALLY_SIGNED') && (
              <div className="space-y-3 rounded-lg border border-white/10 p-4">
                {!voiding ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setVoiding(true)}
                    className="rounded border border-rose-300/30 px-3 py-1.5 text-sm text-rose-200 transition-colors hover:bg-rose-300/10 disabled:opacity-40"
                  >
                    Void record…
                  </button>
                ) : (
                  <>
                    <label htmlFor="void-reason" className="label-dark">
                      Reason for voiding
                    </label>
                    <textarea
                      id="void-reason"
                      value={voidReason}
                      onChange={(e) => setVoidReason(e.target.value)}
                      rows={2}
                      className="input-dark w-full"
                      placeholder="Kept with the record and shown in its audit trail"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        disabled={busy || !voidReason.trim()}
                        onClick={() =>
                          void run(() => voidRecord(detail.id, voidReason.trim()), { changes: true })
                        }
                        className="rounded border border-rose-300/30 px-3 py-1.5 text-sm text-rose-200 transition-colors hover:bg-rose-300/10 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Void this record
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={resetActions}
                        className="rounded border border-white/10 px-3 py-1.5 text-sm text-brand-silver transition-colors hover:bg-white/5 hover:text-white"
                      >
                        Cancel
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

          {canEdit && SUPERSEDABLE.has(detail.status) && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void run(() => supersedeRecord(detail.id), { changes: true })}
              className="btn-primary text-sm disabled:opacity-40"
            >
              Prepare a new version
            </button>
          )}

          <Preview detail={detail} />

          <section>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-white/60">
              History
            </h4>
            <ul className="space-y-1 text-xs text-brand-silver" aria-label="Audit trail">
              {detail.events.map((event, index) => (
                <li key={index}>
                  {formatWhen(event.occurred_at)} · {event.label}
                  {event.actor ? ` · ${event.actor}` : ''}
                </li>
              ))}
            </ul>
          </section>
        </section>
      )}
    </div>
  );
}
