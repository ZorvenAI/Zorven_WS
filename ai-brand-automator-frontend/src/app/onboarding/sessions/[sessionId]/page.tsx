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
import { ArrowLeft, Radio } from 'lucide-react';

import { useAuth } from '@/hooks/useAuth';
import QuestionChecklist from '@/components/onboarding/QuestionChecklist';
import {
  getApprovedQuestionnaire,
  type QuestionnaireDetail,
} from '@/lib/onboarding-sessions';

export default function SessionPage() {
  useAuth();
  const params = useParams<{ sessionId: string }>();
  const sessionId = params?.sessionId;

  const [questionnaire, setQuestionnaire] = useState<QuestionnaireDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!sessionId) {
      // Not `return` on its own: that leaves loading true forever, so a
      // moment without params — or a mis-mounted route — shows "Loading
      // questions…" and never anything else. The empty state is the honest
      // answer when there is no session to load.
      setQuestionnaire(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setQuestionnaire(await getApprovedQuestionnaire(sessionId));
    } catch (error) {
      // Cleared, not left stale. AC-3 wants a re-approved version to replace
      // what is on screen; showing the previous set after a failed refresh
      // would be the same defect with a slower fuse.
      setQuestionnaire(null);
      console.error('Failed to load the approved questionnaire:', error);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

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
        {/*
          §11 gives OnboardingHome an "entry point to the meeting view" and
          E-01 shipped without one. It sits here rather than on the home list
          so the link is next to the questions it opens with, and so it is
          never rendered for a session id that does not resolve.
        */}
        {sessionId && (
          <Link
            href={`/onboarding/sessions/${sessionId}/meeting`}
            className="btn-primary inline-flex items-center gap-2 text-sm"
          >
            <Radio className="h-4 w-4" aria-hidden />
            Open meeting view
          </Link>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-brand-silver">Loading questions…</p>
      ) : (
        <QuestionChecklist
          questions={questionnaire?.questions ?? []}
          version={questionnaire?.version ?? null}
        />
      )}
    </div>
  );
}
