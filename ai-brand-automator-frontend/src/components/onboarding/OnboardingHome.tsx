'use client';

/**
 * OnboardingHome — the landing view at /onboarding (E-01, Design §11).
 *
 * Replaces a redirect. Until now `/onboarding` bounced editors to wizard step
 * 1 and viewers to /chat, so there was no interface at all and a Viewer could
 * not reach onboarding by any route.
 *
 * FR-UI-01: the icon opens this, and this *offers* the manual wizard rather
 * than being it. NFR-COMPAT is the other half — the wizard routes are
 * untouched and still work directly, which E-01 AC-2 requires be asserted by
 * a test rather than by inspection.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  CalendarDays,
  ClipboardList,
  FileText,
  MessageSquare,
  Video,
} from 'lucide-react';

import { useTenantRole } from '@/hooks/useTenantRole';
import {
  listRecordings,
  listSessions,
  wizardDeepLink,
  type MeetingRecordingSummary,
  type OnboardingSessionSummary,
  type SessionStatus,
} from '@/lib/onboarding-sessions';

/**
 * §9.4's states, as chips. Colour carries the same information as the label
 * rather than replacing it — a status a colourblind operator cannot read is
 * not a status.
 */
const STATUS_STYLES: Record<SessionStatus, string> = {
  DRAFT: 'bg-slate-700/60 text-brand-silver',
  PREPARING: 'bg-amber-500/15 text-amber-300',
  READY: 'bg-emerald-500/15 text-emerald-300',
  MEETING_LIVE: 'bg-brand-electric/20 text-brand-electric',
  PROCESSING: 'bg-sky-500/15 text-sky-300',
  REVIEW: 'bg-violet-500/15 text-violet-300',
  COMPLETE: 'bg-emerald-600/15 text-emerald-400',
  ESCALATED: 'bg-rose-500/15 text-rose-300',
  ARCHIVED: 'bg-slate-800/60 text-slate-400',
};

function StatusChip({ status }: { status: SessionStatus }) {
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
        STATUS_STYLES[status] ?? STATUS_STYLES.DRAFT
      }`}
    >
      {status.replace('_', ' ').toLowerCase()}
    </span>
  );
}

/**
 * The calendar pane, before there is a calendar.
 *
 * §11 lists it and AC-1 expects it to render, but scheduling is D-01 — which
 * this story *blocks*, so there is no data source yet and cannot be. A
 * labelled placeholder is the honest shape: leaving the region out would make
 * the page look finished when a quarter of it is not, and stubbing a fake
 * calendar would be worse.
 */
function CalendarPane() {
  return (
    <section
      aria-labelledby="onboarding-calendar-heading"
      className="glass-card p-5"
    >
      <div className="flex items-center gap-2">
        <CalendarDays className="h-4 w-4 text-brand-electric" aria-hidden />
        <h2
          id="onboarding-calendar-heading"
          className="text-sm font-semibold text-white"
        >
          Schedule
        </h2>
      </div>
      <p className="mt-3 text-sm text-brand-silver">
        Booking and calendar sync arrive with the scheduling story. Sessions
        you create here will appear on this pane once it does.
      </p>
    </section>
  );
}

export default function OnboardingHome() {
  const { canEdit: canEditRole } = useTenantRole();
  /**
   * useTenantRole reads TenantContext, which is localStorage-backed, so the
   * server render and the first client render disagree about the role and
   * React reports a hydration mismatch. The project's own rule covers this —
   * "Guard hydration for tenant-role-dependent UI" — and Navigation.tsx
   * already does it. I wrote the role-gated markup without it.
   *
   * Treating an unmounted render as "cannot edit" is the safe direction: the
   * affordances appear a beat late rather than flashing for a Viewer who
   * should never see them.
   */
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => setHasMounted(true), []);
  const canEdit = hasMounted && canEditRole;
  const [sessions, setSessions] = useState<OnboardingSessionSummary[]>([]);
  const [recordings, setRecordings] = useState<MeetingRecordingSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextSessions, nextRecordings] = await Promise.all([
        listSessions(),
        listRecordings(),
      ]);
      setSessions(nextSessions);
      setRecordings(nextRecordings);
    } catch (error) {
      // Clear rather than keep stale rows: a list that silently stops
      // updating is worse than an empty one, because it looks current.
      setSessions([]);
      setRecordings([]);
      console.error('Failed to load onboarding sessions:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-white">Onboarding</h1>
          <p className="mt-1 text-sm text-brand-silver">
            Prepare a meeting, run it, and let the answers fill the brand
            profile — or go straight to the forms.
          </p>
        </div>

        {/*
          Absent for a Viewer, not disabled. AC-3 is explicit that a hidden
          working endpoint behind a greyed-out button does not count, so the
          affordances are not rendered at all.
        */}
        {canEdit && (
          <div className="flex flex-wrap gap-2">
            <Link href="/chat" className="btn-primary inline-flex items-center gap-2">
              <MessageSquare className="h-4 w-4" aria-hidden />
              Prepare in chat
            </Link>
            <Link
              href={wizardDeepLink(sessions[0])}
              className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-4 py-2 text-sm text-brand-silver hover:bg-white/5"
            >
              <FileText className="h-4 w-4" aria-hidden />
              Go to onboarding forms
            </Link>
          </div>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <section aria-labelledby="onboarding-sessions-heading" className="glass-card p-5">
            <div className="flex items-center gap-2">
              <ClipboardList className="h-4 w-4 text-brand-electric" aria-hidden />
              <h2
                id="onboarding-sessions-heading"
                className="text-sm font-semibold text-white"
              >
                Sessions
              </h2>
            </div>

            {loading ? (
              <p className="mt-3 text-sm text-brand-silver">Loading sessions…</p>
            ) : sessions.length === 0 ? (
              <div className="mt-3 space-y-3">
                <p className="text-sm text-brand-silver">
                  No onboarding sessions yet.
                </p>
                {canEdit && (
                  <Link
                    href="/chat"
                    className="inline-flex items-center gap-2 text-sm text-brand-electric hover:underline"
                  >
                    <MessageSquare className="h-4 w-4" aria-hidden />
                    Prepare your first meeting in chat
                  </Link>
                )}
              </div>
            ) : (
              <ul className="mt-3 divide-y divide-white/5">
                {sessions.map((session) => (
                  <li
                    key={session.id}
                    className="flex items-center justify-between gap-3 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm text-white">
                        {session.company ?? 'Unassigned company'}
                      </p>
                      <p className="text-xs text-brand-silver">
                        Updated {new Date(session.updated_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <StatusChip status={session.status} />
                      {canEdit && (
                        <Link
                          href={`/onboarding/sessions/${session.id}`}
                          className="text-sm text-brand-electric hover:underline"
                        >
                          Open
                        </Link>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="onboarding-recordings-heading" className="glass-card p-5">
            <div className="flex items-center gap-2">
              <Video className="h-4 w-4 text-brand-electric" aria-hidden />
              <h2
                id="onboarding-recordings-heading"
                className="text-sm font-semibold text-white"
              >
                Recordings
              </h2>
            </div>
            {loading ? (
              <p className="mt-3 text-sm text-brand-silver">Loading recordings…</p>
            ) : recordings.length === 0 ? (
              <p className="mt-3 text-sm text-brand-silver">
                Recordings appear here after a meeting.
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-white/5">
                {recordings.map((recording) => (
                  <li key={recording.id} className="flex items-center justify-between py-3">
                    <span className="text-sm text-white">{recording.status}</span>
                    <span className="text-xs text-brand-silver">
                      {recording.duration_s
                        ? `${Math.round(recording.duration_s / 60)} min`
                        : '—'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <CalendarPane />
      </div>
    </div>
  );
}
