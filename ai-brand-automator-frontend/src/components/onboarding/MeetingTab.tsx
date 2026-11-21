'use client';

import { useCallback, useEffect, useState } from 'react';

import MeetingView from '@/components/onboarding/MeetingView';
import {
  getApprovedQuestionnaire,
  getSessionConsent,
  grantConsent,
  type ConsentDraft,
  type ConsentState,
  type QuestionnaireDetail,
} from '@/lib/onboarding-sessions';

const CONSENT_POLL_MS = 3000;

interface MeetingTabProps {
  sessionId: string;
  onBack: () => void;
  onRecordingChange?: (active: boolean) => void;
}

export default function MeetingTab({ sessionId, onBack, onRecordingChange }: MeetingTabProps) {
  const [questionnaire, setQuestionnaire] = useState<QuestionnaireDetail | null>(null);
  const [consent, setConsent] = useState<ConsentState | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
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
      console.error('Failed to read consent:', error);
    }
  }, [sessionId]);

  useEffect(() => {
    void readConsent();
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
      sessionId={sessionId}
      consent={consent}
      onGrantConsent={onGrantConsent}
    />
  );
}
