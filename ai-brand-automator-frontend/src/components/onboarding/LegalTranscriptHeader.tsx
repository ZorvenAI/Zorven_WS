'use client';

/**
 * Legal transcript header (O-06).
 *
 * Renders the auto-captured meeting metadata: date, time, attendees, consent.
 * Every field is populated automatically (AC-5: no manual entry).
 */

import { Clock, ShieldCheck, Users } from 'lucide-react';
import type { TranscriptHeader } from '@/lib/onboarding-sessions';

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

  if (!hasAttendees && !hasConsent && !header.date) return null;

  return (
    <div
      className="mb-3 space-y-3 rounded-lg border border-white/10 bg-white/5 p-3"
      data-testid="legal-transcript-header"
    >
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
