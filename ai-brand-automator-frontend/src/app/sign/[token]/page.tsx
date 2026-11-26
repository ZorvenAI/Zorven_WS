'use client';

/**
 * The public signing page. No account: the emailed link is the credential.
 *
 * The link alone shows only which record this is and who it is for. Reading
 * it needs the one-time code emailed to the signatory, and that opens a short
 * session held in memory here — never in storage — which one action spends.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  AlertCircle,
  CheckCircle2,
  FileSignature,
  Loader2,
  Mail,
  XCircle,
} from 'lucide-react';

import RecordDocumentView, { formatWhen } from '@/components/records/RecordDocumentView';
import {
  SigningError,
  getSigningOverview,
  requestSigningCode,
  submitSigning,
  verifySigningCode,
  type OpenedRecord,
  type SigningAction,
  type SigningOverview,
  type SigningRecord,
} from '@/lib/record-signing';

type Choice = 'sign' | 'sign_with_remarks' | 'decline';

const OPEN = new Set(['ISSUED', 'PARTIALLY_SIGNED']);

const CLOSED_MESSAGES: Record<string, string> = {
  COMPLETED: 'This record has been signed by everyone required. A copy was emailed to you.',
  DECLINED: 'This record was declined and can no longer be signed.',
  VOIDED: 'This record was withdrawn by the sender and can no longer be signed.',
  EXPIRED: 'The signing window for this record has closed.',
};

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.';
}

function Shell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-screen bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none" />
      <main
        className={`relative z-10 mx-auto w-full px-4 py-12 ${wide ? 'max-w-3xl' : 'max-w-md'}`}
      >
        {children}
      </main>
    </div>
  );
}

function Notice({ tone, children }: { tone: 'ok' | 'bad'; children: React.ReactNode }) {
  const Icon = tone === 'ok' ? CheckCircle2 : AlertCircle;
  return (
    <div className="glass-card p-8 text-center">
      <Icon
        className={`mx-auto mb-4 h-12 w-12 ${tone === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}
      />
      {children}
    </div>
  );
}

function Header({ overview }: { overview: SigningOverview }) {
  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center gap-2 text-brand-electric">
        <FileSignature className="h-5 w-5" />
        <span className="text-sm font-medium">Meeting record {overview.record_number}</span>
      </div>
      <h1 className="font-heading text-2xl font-bold text-white">
        {overview.agency} and {overview.client}
      </h1>
      <p className="text-sm text-brand-silver/70">
        Meeting of {formatWhen(overview.meeting_started_at)}
        {overview.expires_at ? ` · sign by ${formatWhen(overview.expires_at)}` : ''}
      </p>
    </div>
  );
}

function Signatories({ record }: { record: SigningRecord }) {
  return (
    <ul className="space-y-2 text-sm" aria-label="Signatories">
      {record.signatories.map((s) => (
        <li key={s.id} className="rounded-lg bg-white/5 p-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-white">
              {s.name}
              {s.title ? `, ${s.title}` : ''}
              <span className="text-brand-silver/60"> · {s.party_name}</span>
              {!s.required && <span className="text-brand-silver/60"> · optional</span>}
            </span>
            <span
              className={
                s.status === 'SIGNED'
                  ? 'text-emerald-300'
                  : s.status === 'DECLINED'
                    ? 'text-rose-300'
                    : 'text-brand-silver/60'
              }
            >
              {s.status === 'SIGNED'
                ? `Signed ${formatWhen(s.signed_at)}`
                : s.status === 'DECLINED'
                  ? 'Declined'
                  : 'Not yet signed'}
            </span>
          </div>
          {s.remarks && (
            <p className="mt-2 whitespace-pre-line border-l-2 border-amber-300/50 pl-3 text-amber-100">
              Remarks: {s.remarks}
            </p>
          )}
          {s.decline_reason && (
            <p className="mt-2 whitespace-pre-line border-l-2 border-rose-300/50 pl-3 text-rose-100">
              Reason: {s.decline_reason}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function SignRecordPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? '';

  const [overview, setOverview] = useState<SigningOverview | null>(null);
  const [linkInvalid, setLinkInvalid] = useState(false);
  const [loading, setLoading] = useState(true);

  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [opened, setOpened] = useState<OpenedRecord | null>(null);
  const [result, setResult] = useState<SigningRecord | null>(null);

  const [choice, setChoice] = useState<Choice>('sign');
  const [typedName, setTypedName] = useState('');
  const [consent, setConsent] = useState(false);
  const [remarks, setRemarks] = useState('');
  const [reason, setReason] = useState('');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    getSigningOverview(token)
      .then((data) => {
        if (!cancelled) setOverview(data);
      })
      .catch(() => {
        if (!cancelled) setLinkInvalid(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const sendCode = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const sent = await requestSigningCode(token);
      setSentTo(sent.sent_to);
      setCode('');
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }, [token]);

  const verify = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const record = await verifySigningCode(token, code.trim());
      setOpened(record);
      setTypedName(record.signatory.name);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  };

  const submit = async (action: SigningAction) => {
    if (!opened) return;
    setBusy(true);
    setError('');
    try {
      setResult(await submitSigning(token, opened.session, opened.content_hash, action));
    } catch (err) {
      if (err instanceof SigningError && err.code === 'session_expired') {
        // The session is spent or timed out: confirm the email again.
        setOpened(null);
        setSentTo(null);
      }
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  };

  const signOrDecline = (event: React.FormEvent) => {
    event.preventDefault();
    if (choice === 'decline') {
      void submit({ action: 'decline', reason });
    } else if (choice === 'sign_with_remarks') {
      void submit({ action: 'sign_with_remarks', typed_name: typedName, consent, remarks });
    } else {
      void submit({ action: 'sign', typed_name: typedName, consent });
    }
  };

  if (loading) {
    return (
      <Shell>
        <div className="flex justify-center pt-24">
          <Loader2 className="h-8 w-8 animate-spin text-brand-electric" />
        </div>
      </Shell>
    );
  }

  if (linkInvalid || !overview) {
    return (
      <Shell>
        <Notice tone="bad">
          <h1 className="mb-2 font-heading text-xl font-bold text-white">
            This link cannot be used
          </h1>
          <p className="text-brand-silver/70">
            It may have expired or been replaced by a newer one. Ask the sender to
            send you a new signing link.
          </p>
        </Notice>
      </Shell>
    );
  }

  // ── After an action ──
  if (result) {
    const me = result.signatory;
    const outstanding = result.remarks_to_acknowledge.length > 0;
    return (
      <Shell>
        <Notice tone={me.status === 'DECLINED' ? 'bad' : 'ok'}>
          <h1 className="mb-2 font-heading text-xl font-bold text-white">
            {me.status === 'DECLINED'
              ? 'You declined this record'
              : outstanding
                ? 'Remarks still to acknowledge'
                : 'Thank you'}
          </h1>
          <p className="text-brand-silver/70">
            {me.status === 'DECLINED'
              ? 'The other parties have been told, with your reason.'
              : result.status === 'COMPLETED'
                ? 'Everyone required has signed. A copy of the signed record is on its way to your inbox.'
                : 'Your response is recorded. You will receive the signed record by email once everyone has signed.'}
          </p>
          <p className="mt-4 text-xs text-brand-silver/50">
            Record {result.record_number} · fingerprint {result.content_hash.slice(0, 16)}…
          </p>
        </Notice>
      </Shell>
    );
  }

  // ── Reading and acting ──
  if (opened) {
    const owed = opened.remarks_to_acknowledge;
    return (
      <Shell wide>
        <Header overview={opened} />

        <div className="glass-card mb-6 p-6">
          <RecordDocumentView document={opened.document} full />
        </div>

        <div className="glass-card mb-6 p-6">
          <h2 className="mb-3 font-heading text-lg font-semibold text-white">Signatories</h2>
          <Signatories record={opened} />
        </div>

        {error && (
          <p role="alert" className="mb-4 text-sm text-red-400">
            {error}
          </p>
        )}

        {owed.length > 0 && (
          <div className="glass-card mb-6 p-6">
            <h2 className="mb-2 font-heading text-lg font-semibold text-white">
              Remarks added after you signed
            </h2>
            <p className="mb-4 text-sm text-brand-silver/70">
              {owed.join(', ')} signed with remarks, shown above. The record is not
              complete until you confirm you have read them. This does not change
              what you signed.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void submit({ action: 'acknowledge_remarks' })}
              className="btn-primary text-sm disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'I have read the remarks'}
            </button>
          </div>
        )}

        {opened.can_sign && (
          <form onSubmit={signOrDecline} className="glass-card space-y-4 p-6">
            <h2 className="font-heading text-lg font-semibold text-white">Your response</h2>
            <fieldset className="flex flex-wrap gap-2" aria-label="Response">
              {(
                [
                  ['sign', 'Sign'],
                  ['sign_with_remarks', 'Sign with remarks'],
                  ['decline', 'Decline'],
                ] as const
              ).map(([value, label]) => (
                <label
                  key={value}
                  className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm ${
                    choice === value
                      ? 'border-brand-electric text-white'
                      : 'border-white/15 text-brand-silver'
                  }`}
                >
                  <input
                    type="radio"
                    name="choice"
                    value={value}
                    checked={choice === value}
                    onChange={() => setChoice(value)}
                    className="sr-only"
                  />
                  {label}
                </label>
              ))}
            </fieldset>

            <p className="text-xs text-brand-silver/60">
              The text of the record cannot be changed. If something is wrong, sign
              with remarks to put your view on record, or decline so a corrected
              version can be prepared.
            </p>

            {choice === 'decline' ? (
              <label className="block text-sm">
                <span className="mb-1 block text-white">Why are you declining?</span>
                <textarea
                  required
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg border border-white/15 bg-white/5 p-2 text-white"
                />
              </label>
            ) : (
              <>
                {choice === 'sign_with_remarks' && (
                  <label className="block text-sm">
                    <span className="mb-1 block text-white">Your remarks</span>
                    <textarea
                      required
                      value={remarks}
                      onChange={(e) => setRemarks(e.target.value)}
                      rows={3}
                      className="w-full rounded-lg border border-white/15 bg-white/5 p-2 text-white"
                    />
                  </label>
                )}
                <label className="block text-sm">
                  <span className="mb-1 block text-white">Type your full name to sign</span>
                  <input
                    required
                    minLength={2}
                    value={typedName}
                    onChange={(e) => setTypedName(e.target.value)}
                    autoComplete="name"
                    className="w-full rounded-lg border border-white/15 bg-white/5 p-2 text-white"
                  />
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    required
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                    className="mt-1"
                  />
                  <span>{opened.consent.text}</span>
                </label>
              </>
            )}

            <button
              type="submit"
              disabled={busy}
              className={`w-full text-sm disabled:opacity-50 ${
                choice === 'decline'
                  ? 'rounded-lg border border-rose-300/40 py-2 text-rose-200'
                  : 'btn-primary'
              }`}
            >
              {busy
                ? 'Saving…'
                : choice === 'decline'
                  ? 'Decline to sign'
                  : choice === 'sign_with_remarks'
                    ? 'Sign with remarks'
                    : 'Sign'}
            </button>
          </form>
        )}
      </Shell>
    );
  }

  // ── Before the code ──
  const me = overview.signatory;
  const open = OPEN.has(overview.status);
  const alreadyActed = me.status !== 'PENDING';

  return (
    <Shell>
      <div className="glass-card p-8">
        <Header overview={overview} />
        <p className="mb-6 text-sm text-brand-silver">
          For <span className="text-white">{me.name}</span>, signing for{' '}
          <span className="text-white">{me.party_name}</span>.
        </p>

        {!open ? (
          <p className="text-sm text-brand-silver/80">
            {CLOSED_MESSAGES[overview.status] ?? 'This record can no longer be signed.'}
          </p>
        ) : sentTo === null ? (
          <>
            <p className="mb-4 text-sm text-brand-silver/80">
              {alreadyActed ? (
                'You have already responded. Confirm your email to see progress or acknowledge new remarks.'
              ) : (
                <>
                  To confirm it is you, we will email a one-time code to{' '}
                  <span className="text-white">{me.email_hint}</span>.
                </>
              )}
            </p>
            {error && (
              <p role="alert" className="mb-4 text-sm text-red-400">
                {error}
              </p>
            )}
            <button
              type="button"
              onClick={() => void sendCode()}
              disabled={busy}
              className="btn-primary flex w-full items-center justify-center gap-2 text-sm disabled:opacity-50"
            >
              <Mail className="h-4 w-4" />
              {busy ? 'Sending…' : 'Email me a code'}
            </button>
          </>
        ) : (
          <form onSubmit={verify} className="space-y-4">
            <p className="text-sm text-brand-silver/80">
              We sent a 6-digit code to <span className="text-white">{sentTo}</span>.
              It is valid for 10 minutes.
            </p>
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6}"
              maxLength={6}
              required
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              aria-label="One-time code"
              className="w-full rounded-lg border border-white/15 bg-white/5 p-3 text-center font-mono text-2xl tracking-[0.5em] text-white"
            />
            {error && (
              <p role="alert" className="flex items-center gap-1 text-sm text-red-400">
                <XCircle className="h-4 w-4" />
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={busy || code.length !== 6}
              className="btn-primary w-full text-sm disabled:opacity-50"
            >
              {busy ? 'Checking…' : 'Open the record'}
            </button>
            <button
              type="button"
              onClick={() => void sendCode()}
              disabled={busy}
              className="w-full text-sm text-brand-electric hover:underline disabled:opacity-50"
            >
              Send a new code
            </button>
          </form>
        )}
      </div>
    </Shell>
  );
}
