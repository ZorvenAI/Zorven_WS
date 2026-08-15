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
  getSessionConsent,
  grantConsent,
  type ConsentDraft,
  type ConsentState,
  type QuestionnaireDetail,
} from '@/lib/onboarding-sessions';

/**
 * How often the page re-reads consent (F-01 AC-4).
 *
 * Revocation happens on the session detail page, in another tab or by another
 * operator, so nothing pushes it here. Three seconds, matching the agent's
 * own watch interval: AC-4 gives five, and a five-second poll spends the whole
 * budget waiting.
 */
const CONSENT_POLL_MS = 3000;

export default function MeetingPage() {
  useAuth();
  const params = useParams<{ sessionId: string }>();
  const sessionId = params?.sessionId;

  const [questionnaire, setQuestionnaire] = useState<QuestionnaireDetail | null>(null);
  const [consent, setConsent] = useState<ConsentState | null>(null);
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

  const readConsent = useCallback(async () => {
    if (!sessionId) return;
    try {
      setConsent(await getSessionConsent(sessionId));
    } catch (error) {
      // Not cleared to null on failure: null means "still reading" and hides
      // the banner. A failed poll must not make a session with no consent
      // look fine — it stays on the last state it actually knew.
      console.error('Failed to read consent:', error);
    }
  }, [sessionId]);

  useEffect(() => {
    void readConsent();
    // setTimeout-chained rather than setInterval, matching usePollingJob: an
    // interval stacks requests when one is slow.
    let timer: ReturnType<typeof setTimeout>;
    let cancelled = false;
    const poll = async () => {
      await readConsent();
      if (!cancelled) timer = setTimeout(poll, CONSENT_POLL_MS);
    };
    timer = setTimeout(poll, CONSENT_POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [readConsent]);

  const onGrantConsent = useCallback(
    async (draft: ConsentDraft) => {
      if (!sessionId) return;
      setConsent(await grantConsent(sessionId, draft));
    },
    [sessionId],
  );

  if (loading) {
    return <p className="p-4 text-sm text-brand-silver">Loading questions…</p>;
  }

  return (
    <MeetingView
      questions={questionnaire?.questions ?? []}
      version={questionnaire?.version ?? null}
      backHref={sessionId ? `/onboarding/sessions/${sessionId}` : '/onboarding'}
      consent={consent}
      onGrantConsent={onGrantConsent}
    />
  );
}
