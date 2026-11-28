'use client';

/**
 * Who signs a meeting record, and the agency's part in signing it.
 *
 * On a draft an editor chooses the signatories. Once issued the list is fixed
 * and this shows each person's progress, lets an editor resend links, and lets
 * the logged-in user sign if they are one of the signatories. Which signatory
 * that is comes from the server (`detail.you`), never from this screen.
 */

import { useState } from 'react';
import { Mail, Plus, Trash2 } from 'lucide-react';

import { formatWhen } from '@/components/records/RecordDocumentView';
import {
  remindRecord,
  setSignatories,
  signRecord,
  type AgencySigningAction,
  type RecordDetail,
  type Signatory,
  type SignatoryInput,
} from '@/lib/meeting-records';

const OPEN = new Set(['ISSUED', 'PARTIALLY_SIGNED']);

const METHODS: Record<string, string> = {
  EMAIL_CODE: 'emailed link and one-time code',
  ACCOUNT: 'signed in to the workspace',
};

type Choice = 'sign' | 'sign_with_remarks' | 'decline';

export interface RecordSignatoriesProps {
  detail: RecordDetail;
  canEdit: boolean;
  busy: boolean;
  run: (action: () => Promise<RecordDetail | null | void>) => Promise<void>;
  onNotice: (message: string) => void;
}

function toInput(s: Signatory): SignatoryInput {
  return { party: s.party, name: s.name, title: s.title, email: s.email, required: s.required };
}

const BLANK: SignatoryInput = { party: 'CLIENT', name: '', title: '', email: '', required: true };

function Editor({ detail, busy, run }: Pick<RecordSignatoriesProps, 'detail' | 'busy' | 'run'>) {
  const [rows, setRows] = useState<SignatoryInput[]>(() => detail.signatories.map(toInput));

  const update = (index: number, change: Partial<SignatoryInput>) =>
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...change } : row)));

  return (
    <div className="space-y-3">
      <ul className="space-y-2" aria-label="Signatories to edit">
        {rows.map((row, index) => (
          <li key={index} className="grid gap-2 rounded-lg bg-white/5 p-3 sm:grid-cols-12">
            <select
              aria-label={`Party for signatory ${index + 1}`}
              value={row.party}
              onChange={(e) => update(index, { party: e.target.value as SignatoryInput['party'] })}
              className="input-dark sm:col-span-2"
            >
              <option value="AGENCY">Agency</option>
              <option value="CLIENT">Client</option>
            </select>
            <input
              aria-label={`Name of signatory ${index + 1}`}
              placeholder="Full name"
              value={row.name}
              onChange={(e) => update(index, { name: e.target.value })}
              className="input-dark sm:col-span-3"
            />
            <input
              aria-label={`Title of signatory ${index + 1}`}
              placeholder="Title (optional)"
              value={row.title}
              onChange={(e) => update(index, { title: e.target.value })}
              className="input-dark sm:col-span-2"
            />
            <input
              aria-label={`Email of signatory ${index + 1}`}
              placeholder="Email"
              type="email"
              value={row.email}
              onChange={(e) => update(index, { email: e.target.value })}
              className="input-dark sm:col-span-3"
            />
            <label className="flex items-center gap-1.5 text-xs text-brand-silver sm:col-span-1">
              <input
                type="checkbox"
                checked={row.required}
                onChange={(e) => update(index, { required: e.target.checked })}
              />
              Required
            </label>
            <button
              type="button"
              aria-label={`Remove signatory ${index + 1}`}
              onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
              className="flex items-center justify-center text-brand-silver hover:text-rose-200 sm:col-span-1"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setRows((current) => [...current, { ...BLANK }])}
          className="inline-flex items-center gap-1.5 rounded border border-white/10 px-3 py-1.5 text-xs text-white hover:bg-white/5"
        >
          <Plus className="h-3 w-3" aria-hidden />
          Add signatory
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void run(() => setSignatories(detail.id, rows))}
          className="btn-primary text-xs disabled:opacity-40"
        >
          Save signatories
        </button>
      </div>
      <p className="text-xs text-brand-silver">
        Each person is emailed their own signing link when the record is issued. The
        list is part of what issuing freezes.
      </p>
    </div>
  );
}

function Progress({ detail }: { detail: RecordDetail }) {
  return (
    <ul className="space-y-2 text-sm" aria-label="Signatories">
      {detail.signatories.map((s) => (
        <li key={s.id} className="rounded-lg bg-white/5 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-white">
              {s.name}
              {s.title ? `, ${s.title}` : ''}
              <span className="text-brand-silver"> · {s.party_name} · {s.email}</span>
              {!s.required && <span className="text-brand-silver"> · optional</span>}
              {detail.you === s.id && <span className="text-brand-electric"> · you</span>}
            </span>
            <span
              className={
                s.status === 'SIGNED'
                  ? 'text-emerald-300'
                  : s.status === 'DECLINED'
                    ? 'text-rose-300'
                    : 'text-brand-silver'
              }
            >
              {s.status === 'SIGNED'
                ? `Signed ${formatWhen(s.signed_at)}`
                : s.status === 'DECLINED'
                  ? `Declined ${formatWhen(s.declined_at)}`
                  : detail.status === 'DRAFT'
                    ? 'Not yet sent'
                    : 'Awaiting signature'}
            </span>
          </div>
          {s.status === 'SIGNED' && (
            <p className="mt-1 text-xs text-brand-silver">
              Typed name “{s.typed_name}” · {METHODS[s.method] ?? s.method}
              {s.ip_address ? ` · from ${s.ip_address}` : ''}
            </p>
          )}
          {s.status === 'PENDING' && s.link_expires_at && OPEN.has(detail.status) && (
            <p className="mt-1 text-xs text-brand-silver">
              Link valid until {formatWhen(s.link_expires_at)}
            </p>
          )}
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
          {(detail.remarks_to_acknowledge[String(s.id)] ?? []).length > 0 && (
            <p className="mt-1 text-xs text-amber-200">
              Still to acknowledge remarks by{' '}
              {detail.remarks_to_acknowledge[String(s.id)].join(', ')}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

function SignForm({
  detail,
  me,
  busy,
  run,
}: Pick<RecordSignatoriesProps, 'detail' | 'busy' | 'run'> & { me: Signatory }) {
  const [choice, setChoice] = useState<Choice>('sign');
  const [typedName, setTypedName] = useState(me.name);
  const [consent, setConsent] = useState(false);
  const [remarks, setRemarks] = useState('');
  const [reason, setReason] = useState('');

  const action = (): AgencySigningAction =>
    choice === 'decline'
      ? { action: 'decline', reason: reason.trim() }
      : choice === 'sign_with_remarks'
        ? { action: 'sign_with_remarks', typed_name: typedName, consent, remarks: remarks.trim() }
        : { action: 'sign', typed_name: typedName, consent };

  const ready =
    choice === 'decline'
      ? reason.trim().length > 0
      : consent &&
        typedName.trim().length >= 2 &&
        (choice === 'sign' || remarks.trim().length > 0);

  return (
    <form
      aria-label="Your signature"
      onSubmit={(e) => {
        e.preventDefault();
        void run(() => signRecord(detail.id, detail.content_hash, action()));
      }}
      className="space-y-3 rounded-lg border border-brand-electric/40 p-4"
    >
      <p className="text-sm text-white">You are a signatory on this record.</p>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Response">
        {(
          [
            ['sign', 'Sign'],
            ['sign_with_remarks', 'Sign with remarks'],
            ['decline', 'Decline'],
          ] as const
        ).map(([value, label]) => (
          <label
            key={value}
            className={`cursor-pointer rounded border px-3 py-1 text-xs ${
              choice === value
                ? 'border-brand-electric text-white'
                : 'border-white/15 text-brand-silver'
            }`}
          >
            <input
              type="radio"
              name="agency-choice"
              value={value}
              checked={choice === value}
              onChange={() => setChoice(value)}
              className="sr-only"
            />
            {label}
          </label>
        ))}
      </div>
      {choice === 'decline' ? (
        <label className="block text-sm">
          <span className="label-dark">Reason for declining</span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            className="input-dark w-full"
          />
        </label>
      ) : (
        <>
          {choice === 'sign_with_remarks' && (
            <label className="block text-sm">
              <span className="label-dark">Your remarks</span>
              <textarea
                value={remarks}
                onChange={(e) => setRemarks(e.target.value)}
                rows={2}
                className="input-dark w-full"
              />
            </label>
          )}
          <label className="block text-sm">
            <span className="label-dark">Type your full name to sign</span>
            <input
              value={typedName}
              onChange={(e) => setTypedName(e.target.value)}
              className="input-dark w-full"
            />
          </label>
          <label className="flex items-start gap-2 text-sm text-brand-silver">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-1 h-4 w-4 shrink-0"
            />
            {detail.consent.text}
          </label>
        </>
      )}
      <button
        type="submit"
        disabled={busy || !ready}
        className={`text-sm disabled:cursor-not-allowed disabled:opacity-40 ${
          choice === 'decline'
            ? 'rounded border border-rose-300/30 px-3 py-1.5 text-rose-200'
            : 'btn-primary'
        }`}
      >
        {choice === 'decline'
          ? 'Decline to sign'
          : choice === 'sign_with_remarks'
            ? 'Sign with remarks'
            : 'Sign record'}
      </button>
    </form>
  );
}

export default function RecordSignatories({
  detail,
  canEdit,
  busy,
  run,
  onNotice,
}: RecordSignatoriesProps) {
  const isDraft = detail.status === 'DRAFT';
  const open = OPEN.has(detail.status);
  const me = detail.signatories.find((s) => s.id === detail.you) ?? null;
  const owed = me ? (detail.remarks_to_acknowledge[String(me.id)] ?? []) : [];
  const waiting = detail.signatories.some((s) => s.status === 'PENDING');

  return (
    <section aria-label="Signing" className="space-y-3">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-white/60">
        Signatories
      </h4>

      {isDraft && canEdit ? (
        // Saving recreates the rows, so new ids remount the editor from them.
        <Editor
          key={detail.signatories.map((s) => s.id).join(',')}
          detail={detail}
          busy={busy}
          run={run}
        />
      ) : detail.signatories.length === 0 ? (
        <p className="text-sm text-brand-silver">No signatories have been chosen.</p>
      ) : (
        <Progress detail={detail} />
      )}

      {open && canEdit && waiting && (
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const result = await remindRecord(detail.id);
              onNotice(
                `Sent ${result.sent} new signing link${result.sent === 1 ? '' : 's'}. Earlier links no longer work.`,
              );
              return result;
            })
          }
          className="inline-flex items-center gap-1.5 rounded border border-white/10 px-3 py-1.5 text-xs text-white hover:bg-white/5 disabled:opacity-40"
        >
          <Mail className="h-3 w-3" aria-hidden />
          Send reminder
        </button>
      )}

      {open && me && owed.length > 0 && (
        <div className="space-y-2 rounded-lg border border-amber-300/40 p-4">
          <p className="text-sm text-white">
            {owed.join(', ')} signed with remarks after you did. The record completes
            once you confirm you have read them; this does not change what you signed.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void run(() =>
                signRecord(detail.id, detail.content_hash, { action: 'acknowledge_remarks' }),
              )
            }
            className="btn-primary text-xs disabled:opacity-40"
          >
            I have read the remarks
          </button>
        </div>
      )}

      {open && me && me.status === 'PENDING' && (
        <SignForm key={detail.id} detail={detail} me={me} busy={busy} run={run} />
      )}
    </section>
  );
}
