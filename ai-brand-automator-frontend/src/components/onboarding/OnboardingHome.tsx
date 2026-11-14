'use client';

/**
 * OnboardingHome — the landing view at /onboarding (E-01, Design §11).
 *
 * OIA-UI-01: three-tab layout — Setup Meeting (calendar), Prepare in Chat
 * (embedded AI chat), and a navigation link to the manual wizard forms.
 */

import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  CalendarDays,
  ClipboardList,
  FileText,
  MessageSquare,
  Video,
} from 'lucide-react';

import CalendarPane from '@/components/onboarding/CalendarPane';
import { useTenantRole } from '@/hooks/useTenantRole';
import {
  listRecordings,
  listSessions,
  wizardDeepLink,
  type MeetingRecordingSummary,
  type OnboardingSessionSummary,
  type SessionStatus,
} from '@/lib/onboarding-sessions';

const LazyChatInterface = lazy(() =>
  import('@/components/chat/ChatInterface').then((m) => ({
    default: () => m.ChatInterface({ defaultSidebarOpen: false }),
  })),
);

type OnboardingTab = 'meeting' | 'chat';

const STATUS_STYLES: Record<SessionStatus, string> = {
  DRAFT: 'bg-slate-700/60 text-brand-silver',
  PREPARING: 'bg-amber-500/15 text-amber-300',
  READY: 'bg-emerald-500/15 text-emerald-300',
  MEETING_LIVE: 'bg-brand-electric/20 text-brand-electric',
  GATHERED: 'bg-teal-500/15 text-teal-300',
  PROCESSING: 'bg-sky-500/15 text-sky-300',
  REVIEW_PENDING: 'bg-violet-500/15 text-violet-300',
  CONFIRMED: 'bg-emerald-500/15 text-emerald-400',
  COMPLETED: 'bg-emerald-600/15 text-emerald-400',
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

export default function OnboardingHome() {
  const { canEdit: canEditRole } = useTenantRole();
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => setHasMounted(true), []);
  const canEdit = hasMounted && canEditRole;

  const [sessions, setSessions] = useState<OnboardingSessionSummary[]>([]);
  const [recordings, setRecordings] = useState<MeetingRecordingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<OnboardingTab>('meeting');
  const [chatMounted, setChatMounted] = useState(false);

  useEffect(() => {
    if (activeTab === 'chat') setChatMounted(true);
  }, [activeTab]);

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
      <header>
        <h1 className="text-2xl font-semibold text-white">Onboarding</h1>
        <p className="mt-1 text-sm text-brand-silver">
          Prepare a meeting, run it, and let the answers fill the brand
          profile — or go straight to the forms.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column — sessions + recordings (2/3 width, room for transcription) */}
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
                  <button
                    type="button"
                    onClick={() => setActiveTab('chat')}
                    className="inline-flex items-center gap-2 text-sm text-brand-electric hover:underline"
                  >
                    <MessageSquare className="h-4 w-4" aria-hidden />
                    Prepare your first meeting in chat
                  </button>
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
                        {session.company_name ?? session.company ?? 'Unassigned company'}
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

        {/* Right column — tab bar + calendar/chat (1/3 width, same as original calendar) */}
        <div className="space-y-4">
          {/* Tab bar */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-white/10 p-0.5" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'meeting'}
                onClick={() => setActiveTab('meeting')}
                className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  activeTab === 'meeting'
                    ? 'bg-white/10 text-white'
                    : 'text-brand-silver hover:text-white'
                }`}
              >
                <CalendarDays className="h-3.5 w-3.5" aria-hidden />
                Setup Meeting
              </button>
              {canEdit && (
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === 'chat'}
                  onClick={() => setActiveTab('chat')}
                  className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                    activeTab === 'chat'
                      ? 'bg-white/10 text-white'
                      : 'text-brand-silver hover:text-white'
                  }`}
                >
                  <MessageSquare className="h-3.5 w-3.5" aria-hidden />
                  Prepare in Chat
                </button>
              )}
            </div>
            {canEdit && (
              <Link
                href={wizardDeepLink(sessions[0])}
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-xs text-brand-silver hover:bg-white/5"
              >
                <FileText className="h-3.5 w-3.5" aria-hidden />
                Go to Forms
              </Link>
            )}
          </div>

          {/* Tab content */}
          <div role="tabpanel">
            {activeTab === 'meeting' && <CalendarPane />}
            {chatMounted && (
              <div className={activeTab === 'chat' ? '' : 'hidden'}>
                <div className="h-[calc(100vh-12rem)] rounded-lg border border-white/10 overflow-hidden">
                  <Suspense
                    fallback={
                      <div className="flex h-full items-center justify-center bg-brand-midnight">
                        <div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-electric/30 border-t-brand-electric" />
                      </div>
                    }
                  >
                    <LazyChatInterface />
                  </Suspense>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
