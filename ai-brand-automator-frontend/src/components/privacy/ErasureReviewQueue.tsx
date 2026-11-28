'use client';

/**
 * Erasure review queue.
 *
 * GDPR erasure requests that were held back because the person's sessions
 * contain signed meeting records. An owner or admin decides each one:
 *
 * - Keep under legal hold, until a date (defaults to the workspace's hold
 *   period). The request comes back here when the hold runs out.
 * - Erase anyway: deletes the signed records and their audit trail for good.
 *   The subject's name has to be typed to confirm.
 *
 * Both need a written reason, and both are final.
 */

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, FileLock2, Loader2, ShieldAlert, Trash2 } from 'lucide-react';

import {
  MIN_REASON_CHARS,
  eraseAnyway,
  keepUnderHold,
  listErasureReviews,
  type ErasureReviewItem,
  type ReviewStatus,
} from '@/lib/erasure-review';

type Tab = 'PENDING' | 'DECIDED';
type Form = { id: number; kind: 'keep' | 'erase' } | null;

const STATUS_LABEL: Record<ReviewStatus, string> = {
  PENDING: 'Awaiting review',
  KEPT: 'Kept under legal hold',
  ERASED: 'Erased on review',
};

function formatDate(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong. Try again.';
}

export default function ErasureReviewQueue() {
  const [tab, setTab] = useState<Tab>('PENDING');
  const [pending, setPending] = useState<ErasureReviewItem[]>([]);
  const [decided, setDecided] = useState<ErasureReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(null);
  const [reason, setReason] = useState('');
  const [holdUntil, setHoldUntil] = useState('');
  const [confirmName, setConfirmName] = useState('');

  const load = useCallback(async () => {
    setError(null);
    try {
      const [open, kept, erased] = await Promise.all([
        listErasureReviews('PENDING'),
        listErasureReviews('KEPT'),
        listErasureReviews('ERASED'),
      ]);
      setPending(open);
      setDecided(
        [...kept, ...erased].sort((a, b) =>
          (b.reviewed_at ?? '').localeCompare(a.reviewed_at ?? ''),
        ),
      );
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = (item: ErasureReviewItem, kind: 'keep' | 'erase') => {
    setForm({ id: item.id, kind });
    setReason('');
    setConfirmName('');
    setHoldUntil(item.default_hold_until);
    setError(null);
    setNotice(null);
  };

  const submit = async (item: ErasureReviewItem) => {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      if (form.kind === 'keep') {
        await keepUnderHold(item.id, reason.trim(), holdUntil || undefined);
        setNotice(`Kept the records for ${item.subject_name} under legal hold.`);
      } else {
        await eraseAnyway(item.id, reason.trim(), confirmName);
        setNotice(
          `Erasing the held data for ${item.subject_name}. It moves to Decided once finished.`,
        );
      }
      setForm(null);
      await load();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  };

  const reasonOk = reason.trim().length >= MIN_REASON_CHARS;

  if (loading) {
    return (
      <div className="glass-card flex items-center gap-2 p-6 text-brand-silver">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading erasure requests…
      </div>
    );
  }

  return (
    <section className="glass-card space-y-4 p-6" aria-labelledby="erasure-review-title">
      <div>
        <h3
          id="erasure-review-title"
          className="flex items-center gap-2 text-sm font-semibold text-white"
        >
          <FileLock2 className="h-4 w-4 text-brand-electric" aria-hidden />
          Erasure requests held for signed records
        </h3>
        <p className="mt-1 text-xs text-brand-silver">
          These people asked for their data to be erased, but some of their meetings have
          signed records. Decide each one within a month of the request.
        </p>
      </div>

      <div role="tablist" aria-label="Erasure requests" className="flex gap-2">
        {(['PENDING', 'DECIDED'] as Tab[]).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={`rounded px-3 py-1.5 text-sm transition-colors ${
              tab === value
                ? 'bg-brand-electric/15 text-white ring-1 ring-brand-electric/40'
                : 'text-brand-silver hover:bg-white/5 hover:text-white'
            }`}
          >
            {value === 'PENDING' ? `To decide (${pending.length})` : 'Decided'}
          </button>
        ))}
      </div>

      {notice && (
        <p
          role="status"
          className="rounded border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300"
        >
          {notice}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300"
        >
          {error}
        </p>
      )}

      {tab === 'PENDING' && pending.length === 0 && (
        <p className="text-sm text-brand-silver">Nothing is waiting for a decision.</p>
      )}

      {tab === 'PENDING' && pending.length > 0 && (
        <ul className="space-y-3" aria-label="Requests to decide">
          {pending.map((item) => (
            <li
              key={item.id}
              data-testid={`review-${item.id}`}
              data-overdue={item.overdue ? 'true' : 'false'}
              className={`space-y-3 rounded border p-4 ${
                item.overdue ? 'border-yellow-500/40 bg-yellow-500/5' : 'border-white/10'
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-white">{item.subject_name}</p>
                  <p className="text-xs text-brand-silver">
                    Requested {formatDate(item.requested_at)} · waiting {item.days_waiting}{' '}
                    {item.days_waiting === 1 ? 'day' : 'days'}
                    {item.reason ? ` · ${item.reason}` : ''}
                  </p>
                </div>
                {item.overdue && (
                  <span className="flex items-center gap-1 text-xs text-yellow-300">
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
                    Close to the one-month deadline
                  </span>
                )}
              </div>

              <ul className="space-y-1 text-xs text-brand-silver" aria-label="Held sessions">
                {item.held.map((session) => (
                  <li key={session.session_id}>
                    {session.company_name || `Session ${session.session_id}`}:{' '}
                    {session.records.map((r) => r.record_number).join(', ') || 'no records'}
                  </li>
                ))}
              </ul>

              {item.erase_in_progress && (
                <p className="text-xs text-brand-electric">Erasure was chosen and is running.</p>
              )}
              {item.last_error && (
                <p className="text-xs text-rose-300">
                  The last erasure attempt failed: {item.last_error}
                </p>
              )}

              {form?.id !== item.id && !item.erase_in_progress && (
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => open(item, 'keep')}
                    className="rounded border border-white/15 px-3 py-1.5 text-sm text-white hover:bg-white/5 disabled:opacity-40"
                  >
                    Keep under legal hold
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => open(item, 'erase')}
                    className="rounded border border-rose-500/40 px-3 py-1.5 text-sm text-rose-300 hover:bg-rose-500/10 disabled:opacity-40"
                  >
                    Erase anyway
                  </button>
                </div>
              )}

              {form?.id === item.id && (
                <form
                  className="space-y-3 rounded border border-white/10 p-3"
                  aria-label={form.kind === 'keep' ? 'Keep under legal hold' : 'Erase anyway'}
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submit(item);
                  }}
                >
                  {form.kind === 'erase' && (
                    <p className="flex items-start gap-2 text-xs text-rose-300">
                      <ShieldAlert className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden />
                      This permanently deletes the signed records listed above, their audit
                      trail, and the recordings they came from. Only the record numbers and
                      fingerprints are kept, as proof they existed. This cannot be undone.
                    </p>
                  )}

                  <div>
                    <label
                      htmlFor={`reason-${item.id}`}
                      className="block text-xs text-brand-silver"
                    >
                      Reason (at least {MIN_REASON_CHARS} characters)
                    </label>
                    <textarea
                      id={`reason-${item.id}`}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      rows={2}
                      className="mt-1 w-full rounded border border-white/15 bg-transparent px-3 py-2 text-sm text-white"
                    />
                  </div>

                  {form.kind === 'keep' && (
                    <div>
                      <label
                        htmlFor={`hold-${item.id}`}
                        className="block text-xs text-brand-silver"
                      >
                        Keep until
                      </label>
                      <input
                        id={`hold-${item.id}`}
                        type="date"
                        value={holdUntil}
                        onChange={(e) => setHoldUntil(e.target.value)}
                        className="mt-1 rounded border border-white/15 bg-transparent px-3 py-2 text-sm text-white"
                      />
                    </div>
                  )}

                  {form.kind === 'erase' && (
                    <div>
                      <label
                        htmlFor={`confirm-${item.id}`}
                        className="block text-xs text-brand-silver"
                      >
                        Type the name <strong className="text-white">{item.subject_name}</strong>{' '}
                        to confirm
                      </label>
                      <input
                        id={`confirm-${item.id}`}
                        value={confirmName}
                        onChange={(e) => setConfirmName(e.target.value)}
                        autoComplete="off"
                        className="mt-1 w-full rounded border border-white/15 bg-transparent px-3 py-2 text-sm text-white"
                      />
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={
                        busy ||
                        !reasonOk ||
                        (form.kind === 'erase' && confirmName !== item.subject_name) ||
                        (form.kind === 'keep' && !holdUntil)
                      }
                      className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-40 ${
                        form.kind === 'erase'
                          ? 'bg-rose-600 text-white hover:bg-rose-500'
                          : 'btn-primary'
                      }`}
                    >
                      {form.kind === 'erase' && <Trash2 className="h-4 w-4" aria-hidden />}
                      {form.kind === 'erase' ? 'Erase permanently' : 'Confirm legal hold'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm(null)}
                      className="text-sm text-brand-silver hover:text-white"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </li>
          ))}
        </ul>
      )}

      {tab === 'DECIDED' && decided.length === 0 && (
        <p className="text-sm text-brand-silver">No decisions yet.</p>
      )}

      {tab === 'DECIDED' && decided.length > 0 && (
        <ul className="space-y-3" aria-label="Decided requests">
          {decided.map((item) => (
            <li key={item.id} className="space-y-1 rounded border border-white/10 p-4 text-xs">
              <p className="text-sm font-medium text-white">{item.subject_name}</p>
              <p className="text-brand-silver">
                {STATUS_LABEL[item.review_status]} by {item.reviewed_by ?? 'unknown'} on{' '}
                {formatDate(item.reviewed_at)}
                {item.review_status === 'KEPT' && ` · until ${formatDate(item.hold_until)}`}
              </p>
              <p className="text-brand-silver">Reason: {item.review_reason}</p>
              {item.review_status === 'ERASED' && item.erased_signed_records.length > 0 && (
                <p className="text-brand-silver">
                  Erased records:{' '}
                  {item.erased_signed_records.map((r) => r.record_number).join(', ')}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
