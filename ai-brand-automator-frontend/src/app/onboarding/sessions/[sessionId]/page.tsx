'use client';

/**
 * /onboarding/sessions/[sessionId] — one session, with its approved questions.
 *
 * This route is also the fix for a dangling link: E-01 rendered an "Open"
 * action pointing here before the page existed, so it 404'd from the moment
 * that PR merged. C-05 needs the page anyway — it is where QuestionChecklist
 * lives — but the link should not have shipped ahead of it.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, ClipboardCheck, Radio } from 'lucide-react';

import { useAuth } from '@/hooks/useAuth';
import { useLibraryPolling } from '@/hooks/useLibraryPolling';
import { useTenantRole } from '@/hooks/useTenantRole';
import QuestionChecklist from '@/components/onboarding/QuestionChecklist';
import RecordingsLibrary from '@/components/onboarding/RecordingsLibrary';
import ProcessButton from '@/components/onboarding/ProcessButton';
import {
  getApprovedQuestionnaire,
  getSessionDetail,
  type QuestionnaireDetail,
  type SessionDetail,
} from '@/lib/onboarding-sessions';

export default function SessionPage() {
  useAuth();
  const params = useParams<{ sessionId: string }>();
  const sessionId = params?.sessionId;

  const [questionnaire, setQuestionnaire] = useState<QuestionnaireDetail | null>(null);
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const library = useLibraryPolling(sessionId ?? null);
  const { isAdmin } = useTenantRole();

  const load = useCallback(async () => {
    if (!sessionId) {
      setQuestionnaire(null);
      setSession(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [q, s] = await Promise.all([
        getApprovedQuestionnaire(sessionId),
        getSessionDetail(sessionId),
      ]);
      setQuestionnaire(q);
      setSession(s);
    } catch (error) {
      setQuestionnaire(null);
      setSession(null);
      console.error('Failed to load session:', error);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll session status while PROCESSING (J-01, AC-5).
  useEffect(() => {
    if (!sessionId || session?.status !== 'PROCESSING') return;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const updated = await getSessionDetail(sessionId);
        setSession(updated);
        if (updated.status === 'PROCESSING') {
          timer = setTimeout(poll, 3000);
        }
      } catch {
        timer = setTimeout(poll, 5000);
      }
    };
    timer = setTimeout(poll, 3000);
    return () => clearTimeout(timer);
  }, [sessionId, session?.status]);

  return (
    <div className="space-y-6">
      <Link
        href="/onboarding"
        className="inline-flex items-center gap-2 text-sm text-brand-silver hover:text-white"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Onboarding
      </Link>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-white">Session</h1>
        <div className="flex flex-wrap gap-2">
          {sessionId && session && (
            session.status === 'REVIEW_PENDING' ||
            session.status === 'CONFIRMED' ||
            session.status === 'COMPLETED'
          ) && (
            <Link
              href={`/onboarding/sessions/${sessionId}/review`}
              className="btn-primary inline-flex items-center gap-2 text-sm"
            >
              <ClipboardCheck className="h-4 w-4" aria-hidden />
              Review findings
            </Link>
          )}
          {sessionId && (
            <Link
              href={`/onboarding/sessions/${sessionId}/meeting`}
              className="inline-flex items-center gap-2 rounded border border-white/10 px-3 py-1.5 text-sm text-brand-silver hover:bg-white/5 hover:text-white"
            >
              <Radio className="h-4 w-4" aria-hidden />
              Open meeting view
            </Link>
          )}
        </div>
      </div>

      {sessionId && session && (
        <div className="glass-card p-5">
          <ProcessButton
            sessionId={sessionId}
            status={session.status}
            coverage={questionnaire?.coverage ?? null}
            onDispatch={load}
          />
        </div>
      )}

      {loading ? (
        <p className="text-sm text-brand-silver">Loading questions…</p>
      ) : (
        <QuestionChecklist
          questions={questionnaire?.questions ?? []}
          version={questionnaire?.version ?? null}
        />
      )}

      {(library.recordings.length > 0 || library.captures.length > 0) && (
        <div className="glass-card p-5">
          <h2 className="mb-3 text-sm font-semibold text-white">
            Recordings and captures
          </h2>
          <RecordingsLibrary
            recordings={library.recordings}
            captures={library.captures}
            canDelete={isAdmin}
            onDeleted={library.refresh}
          />
        </div>
      )}
    </div>
  );
}
