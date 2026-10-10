'use client';

/**
 * Legal transcript header (O-06).
 *
 * Renders the auto-captured meeting metadata: date, time, attendees, consent.
 * Every field is populated automatically (AC-5: no manual entry).
 */

import { AlertTriangle, Clock, ShieldCheck, Users } from 'lucide-react';
import type { TranscriptHeader } from '@/lib/onboarding-sessions';

/** Whole seconds as "4m 27s", for a notice an operator has to act on. */
function formatMissing(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m === 0) return `${s}s`;
  return s === 0 ? `${m}m` : `${m}m ${s}s`;
}

export interface LegalTranscriptHeaderProps {
  header: TranscriptHeader;
}

function formatConsentMethod(method: string): string {
  return method
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return iso;
  }
}

export default function LegalTranscriptHeader({
  header,
}: LegalTranscriptHeaderProps) {
  const hasAttendees = header.attendees.length > 0;
  const hasConsent = header.consent != null;
  const completeness = header.transcript_completeness;
  // #662: `complete` and a missing block both render nothing. An absent block
  // means the backend predates coverage reporting, and inventing a warning for
  // it would be as wrong as the silence this fixes.
  const incomplete =
    completeness != null && completeness.state !== 'complete';

  if (!hasAttendees && !hasConsent && !header.date && !incomplete) return null;

  return (
    <div
      className="mb-3 space-y-3 rounded-lg border border-white/10 bg-white/5 p-3"
      data-testid="legal-transcript-header"
    >
      {/* #662 · stated first, because every field below it describes a
          transcript whose extent this qualifies. */}
      {incomplete && completeness && (
        <div
          className={`flex items-start gap-2 rounded-md border p-2 ${
            completeness.state === 'partial'
              ? 'border-amber-500/40 bg-amber-500/10'
              : 'border-white/15 bg-white/5'
          }`}
          data-testid="transcript-completeness-notice"
          role="status"
        >
          <AlertTriangle
            className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
              completeness.state === 'partial'
                ? 'text-amber-400'
                : 'text-brand-silver'
            }`}
            aria-hidden
          />
          <div className="text-sm">
            <p className="font-medium text-white">
              {completeness.state === 'partial'
                ? `Partial transcript${
                    formatMissing(completeness.missing_s)
                      ? ` — ${formatMissing(completeness.missing_s)} not transcribed`
                      : ''
                  }`
                : 'Transcript coverage not assessed'}
            </p>
            <p className="text-brand-silver">{completeness.note}</p>
          </div>
        </div>
      )}

      {/* Date & session */}
      <div className="flex items-start gap-2">
        <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-silver" aria-hidden />
        <div className="text-sm">
          <p className="font-medium text-white">
            {header.session_company
              ? `Meeting — ${header.session_company}`
              : 'Meeting Transcript'}
          </p>
          <p className="text-brand-silver">
            {formatDate(header.started_at_iso)}
            {header.time_utc ? ` · ${header.time_utc}` : ''}
          </p>
        </div>
      </div>

      {/* Attendees */}
      {hasAttendees && (
        <div className="flex items-start gap-2">
          <Users className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-silver" aria-hidden />
          <div className="text-sm">
            <p className="mb-1 font-medium text-white">Attendees</p>
            <ul className="space-y-0.5">
              {header.attendees.map((a, i) => (
                <li key={i} className="text-brand-silver">
                  <span className="text-white">{a.name}</span>
                  {a.role && (
                    <span className="ml-1 text-brand-silver">
                      ({a.role})
                    </span>
                  )}
                  {a.mic_label && (
                    <span className="ml-1 text-brand-silver/60">
                      — {a.mic_label}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Consent */}
      {hasConsent && header.consent && (
        <div className="flex items-start gap-2">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" aria-hidden />
          <div className="text-sm">
            <p className="mb-0.5 font-medium text-white">Consent</p>
            <p className="text-brand-silver">
              {header.consent.subject_name && (
                <span>{header.consent.subject_name} · </span>
              )}
              {formatConsentMethod(header.consent.method)}
              {header.consent.granted_at && (
                <span> · {formatDateTime(header.consent.granted_at)}</span>
              )}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
