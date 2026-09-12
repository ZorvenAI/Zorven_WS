'use client';

import { useEffect, useState } from 'react';
import {
  Camera,
  ExternalLink,
  FileCheck2,
  Mic,
  ShieldCheck,
  Video,
} from 'lucide-react';

import {
  getSessionDetail,
  listSessionCaptures,
  listSessionRecordings,
  type CapturedMedia,
  type ConsentState,
  type RecordingItem,
} from '@/lib/onboarding-sessions';

export interface MeetingEvidenceProps {
  sessionId: string;
}

const CONSENT_METHOD_LABELS: Record<string, string> = {
  VERBAL_RECORDED: 'Verbal (recorded)',
  CHECKBOX: 'Written consent',
};

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function StatusChip({ status }: { status: string }) {
  switch (status) {
    case 'RECORDING':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-red-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-400" />
          Recording
        </span>
      );
    case 'UPLOADED':
      return <span className="text-xs text-yellow-400">Processing</span>;
    case 'TRANSCRIBED':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-green-400">
          Transcribed
        </span>
      );
    case 'SUMMARIZED':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-green-400">
          Ready
        </span>
      );
    case 'FAILED':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-red-400">
          Failed
        </span>
      );
    default:
      return <span className="text-xs text-brand-silver">{status}</span>;
  }
}

export default function MeetingEvidence({ sessionId }: MeetingEvidenceProps) {
  const [recordings, setRecordings] = useState<RecordingItem[]>([]);
  const [captures, setCaptures] = useState<CapturedMedia[]>([]);
  const [consent, setConsent] = useState<ConsentState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchEvidence() {
      setLoading(true);
      try {
        const [recs, caps, detail] = await Promise.all([
          listSessionRecordings(sessionId),
          listSessionCaptures(sessionId),
          getSessionDetail(sessionId),
        ]);
        if (cancelled) return;
        setRecordings(recs);
        setCaptures(caps);
        setConsent(detail.consent);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchEvidence();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (loading) {
    return (
      <div className="bg-white/5 border border-white/10 rounded-lg p-6" data-testid="meeting-evidence-loading">
        <div className="flex items-center gap-2 text-brand-silver">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-electric border-t-transparent" />
          <span className="text-sm">Loading meeting evidence…</span>
        </div>
      </div>
    );
  }

  if (error || (recordings.length === 0 && captures.length === 0)) {
    return null;
  }

  return (
    <div className="bg-white/5 border border-white/10 rounded-lg p-6" data-testid="meeting-evidence">
      <h2 className="font-heading text-xl font-semibold text-white mb-4 flex items-center gap-2">
        <FileCheck2 className="h-5 w-5 text-brand-electric" aria-hidden />
        Meeting Evidence
      </h2>

      {consent?.granted && consent.granted_at && (
        <div
          className="mb-4 flex items-center gap-2 rounded border border-green-500/20 bg-green-500/5 px-4 py-2 text-sm text-green-300"
          data-testid="consent-reference"
        >
          <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden />
          <span>
            Consent recorded:{' '}
            {consent.method
              ? CONSENT_METHOD_LABELS[consent.method] ?? consent.method
              : 'Unknown method'}
            {' on '}
            {new Date(consent.granted_at).toLocaleDateString(undefined, {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
            })}
          </span>
        </div>
      )}

      {recordings.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wider text-brand-silver">
            Recordings
          </h3>
          <ul className="space-y-1.5" data-testid="evidence-recordings">
            {recordings.map((r) => (
              <li
                key={r.id}
                className="flex items-center gap-2 rounded border border-white/10 px-3 py-2 text-sm"
              >
                <Mic
                  aria-hidden
                  className="h-3.5 w-3.5 shrink-0 text-brand-silver"
                />
                <span className="text-white">
                  {formatDuration(r.duration_s)}
                </span>
                <StatusChip status={r.status} />
                <span className="flex-1" />
                {r.has_summary && (
                  <a
                    href={`/onboarding/sessions/${sessionId}?recording=${r.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-brand-electric hover:underline"
                  >
                    View summary
                    <ExternalLink className="h-3 w-3" aria-hidden />
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {captures.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wider text-brand-silver">
            Captures
          </h3>
          <ul className="space-y-1.5" data-testid="evidence-captures">
            {captures.map((c) => (
              <li
                key={c.id}
                className="flex items-center gap-2 rounded border border-white/10 px-3 py-2 text-sm"
              >
                {c.file_type === 'video' ? (
                  <Video
                    aria-hidden
                    className="h-3.5 w-3.5 shrink-0 text-brand-silver"
                  />
                ) : (
                  <Camera
                    aria-hidden
                    className="h-3.5 w-3.5 shrink-0 text-brand-silver"
                  />
                )}
                <a
                  href={`/onboarding/sessions/${sessionId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="truncate text-white hover:text-brand-electric"
                >
                  {c.file_name}
                </a>
                <span className="shrink-0 rounded bg-brand-electric/20 px-1.5 py-0.5 text-xs text-brand-electric">
                  {c.usage_tag.replace(/_/g, ' ')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
