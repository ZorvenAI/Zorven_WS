'use client';

/**
 * /onboarding/sessions/[sessionId]/meeting — the live meeting view (E-02).
 *
 * Nested under the session because a meeting is always a meeting *for* one,
 * and the session page is already where its approved questions live.
 *
 * The questions are real — C-05's endpoint serves them. Everything else on
 * this page is a placeholder with an owner: the feedback stream is F-04's to
 * fill, the rail's controls are F-02's and H-01's. E-02 delivers the shape.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

import { useAuth } from '@/hooks/useAuth';
import MeetingView from '@/components/onboarding/MeetingView';
import {
  getApprovedQuestionnaire,
  type QuestionnaireDetail,
} from '@/lib/onboarding-sessions';

export default function MeetingPage() {
  useAuth();
  const params = useParams<{ sessionId: string }>();
  const sessionId = params?.sessionId;

  const [questionnaire, setQuestionnaire] = useState<QuestionnaireDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!sessionId) {
      // Same shape as the session page, and for the same reason: returning
      // early with `loading` still true leaves "Loading questions…" on screen
      // for ever.
      setQuestionnaire(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setQuestionnaire(await getApprovedQuestionnaire(sessionId));
    } catch (error) {
      setQuestionnaire(null);
      console.error('Failed to load the approved questionnaire:', error);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="p-4 text-sm text-brand-silver">Loading questions…</p>;
  }

  return (
    <MeetingView
      questions={questionnaire?.questions ?? []}
      version={questionnaire?.version ?? null}
      backHref={sessionId ? `/onboarding/sessions/${sessionId}` : '/onboarding'}
    />
  );
}
