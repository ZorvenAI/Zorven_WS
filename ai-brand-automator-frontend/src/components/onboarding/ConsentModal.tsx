'use client';

/**
 * Consent capture, before the microphone can open (F-01, AC-2).
 *
 * A record, not a checkbox. FR-GDPR-01 wants "who consented, when, and to what
 * scope", and a boolean answers none of those. The subject's name is typed
 * here, stored on the ConsentRecord, and never leaves the tenant-scoped
 * database — the event stream gets a keyed hash instead.
 *
 * Consent is per session and never inherited. If the operator has run three
 * meetings with the same brand owner, they record consent three times: B-07
 * made that structural (the FK is to session), and this is where it becomes
 * visible to a person.
 *
 * This is the one modal the meeting view is allowed to show. §11's rule is
 * that nothing *the agent produces* may steal focus; this is the operator's
 * own deliberate action, and it must have their attention — the microphone
 * cannot open until it does.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ShieldCheck, X } from 'lucide-react';

import {
  ONBOARDING_CONSENT_SCOPE,
  type ConsentDraft,
  type ConsentMethod,
} from '@/lib/onboarding-sessions';

export interface ConsentModalProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: (draft: ConsentDraft) => Promise<void> | void;
  saving?: boolean;
  error?: string | null;
}

const METHODS: { value: ConsentMethod; label: string; hint: string }[] = [
  {
    value: 'VERBAL_RECORDED',
    label: 'Spoken aloud',
    hint: 'They said yes, and the recording will carry it.',
  },
  {
    value: 'CHECKBOX',
    label: 'In writing',
    hint: 'They agreed in a form, email or signed note.',
  },
];

export default function ConsentModal({
  open,
  onCancel,
  onConfirm,
  saving = false,
  error = null,
}: ConsentModalProps) {
  const [subjectName, setSubjectName] = useState('');
  const [method, setMethod] = useState<ConsentMethod>('VERBAL_RECORDED');
  const nameInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) nameInput.current?.focus();
  }, [open]);

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      const name = subjectName.trim();
      if (!name) return;
      await onConfirm({
        subject_name: name,
        method,
        scope: ONBOARDING_CONSENT_SCOPE,
      });
    },
    [subjectName, method, onConfirm],
  );

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="consent-heading"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <form
        onSubmit={submit}
        className="glass-card w-full max-w-md space-y-4 p-6"
      >
        <div className="flex items-start justify-between gap-3">
          <h2
            id="consent-heading"
            className="flex items-center gap-2 text-base font-semibold text-white"
          >
            <ShieldCheck className="h-5 w-5 text-brand-electric" aria-hidden />
            Record consent
          </h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="text-brand-silver hover:text-white"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div>
          <label
            htmlFor="subject-name"
            className="block text-sm text-brand-silver"
          >
            Who is consenting?
          </label>
          <input
            id="subject-name"
            ref={nameInput}
            value={subjectName}
            onChange={(event) => setSubjectName(event.target.value)}
            required
            className="mt-1 w-full rounded border border-white/15 bg-transparent px-3 py-2 text-sm text-white"
          />
          <p className="mt-1 text-xs text-brand-silver">
            Their name is stored with the consent record and is never sent to
            the agent or to analytics.
          </p>
        </div>

        <fieldset>
          <legend className="text-sm text-brand-silver">
            How did they agree?
          </legend>
          <div className="mt-2 space-y-2">
            {METHODS.map((option) => (
              <label
                key={option.value}
                className="flex items-start gap-2 text-sm text-white"
              >
                <input
                  type="radio"
                  name="consent-method"
                  value={option.value}
                  checked={method === option.value}
                  onChange={() => setMethod(option.value)}
                  className="mt-1"
                />
                <span>
                  {option.label}
                  <span className="block text-xs text-brand-silver">
                    {option.hint}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {/*
          The scope is stated, not implied. This sentence and
          ONBOARDING_CONSENT_SCOPE have to say the same thing — consent for
          something the operator did not read out is not consent.
        */}
        <p className="rounded border border-white/10 p-3 text-xs text-brand-silver">
          Confirming records that they agreed to this meeting being{' '}
          <strong className="text-white">recorded</strong>,{' '}
          <strong className="text-white">transcribed</strong> and{' '}
          <strong className="text-white">processed</strong> to build their brand
          profile. They can withdraw at any time, and recording stops when they
          do.
        </p>

        {error && (
          <p role="alert" className="text-sm text-rose-300">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded px-3 py-2 text-sm text-brand-silver hover:text-white"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || !subjectName.trim()}
            className="btn-primary text-sm disabled:opacity-50"
          >
            {saving ? 'Recording…' : 'Record consent'}
          </button>
        </div>
      </form>
    </div>
  );
}
