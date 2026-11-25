'use client';

import { useCallback, useEffect, useState } from 'react';
import { FileText, Radio } from 'lucide-react';

import { apiClient } from '@/lib/api';
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

interface SessionOverviewTabProps {
  sessionId: string;
  onOpenMeeting: () => void;
  onOpenReview: () => void;
}

export default function SessionOverviewTab({
  sessionId,
  onOpenMeeting,
  onOpenReview,
}: SessionOverviewTabProps) {
  const [questionnaire, setQuestionnaire] = useState<QuestionnaireDetail | null>(null);
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const [transcriptClean, setTranscriptClean] = useState<string>('');

  const library = useLibraryPolling(sessionId);
  const { isAdmin } = useTenantRole();

  const load = useCallback(async () => {
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

  useEffect(() => {
    if (session?.status !== 'PROCESSING') return;
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

  useEffect(() => {
    const hasSummarized = library.recordings.some(
      (r) => r.status === 'SUMMARIZED',
    );
    if (!hasSummarized) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await apiClient.get(
          `/onboarding/sessions/${sessionId}/description/`,
        );
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as {
          meetings?: { transcript_clean?: string }[];
        };
        if (!cancelled) {
          setTranscriptClean(data.meetings?.at(-1)?.transcript_clean ?? '');
        }
      } catch {
        /* non-critical */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, library.recordings]);

  const canMeet =
    session?.status === 'READY' ||
    session?.status === 'MEETING_LIVE' ||
    session?.status === 'GATHERED';

  const canReview =
    session?.status === 'REVIEW_PENDING' ||
    session?.status === 'CONFIRMED' ||
    session?.status === 'COMPLETED';

  return (
    <div className="space-y-5 overflow-y-auto p-5">
      {/* Quick actions */}
      <div className="flex flex-wrap gap-2">
        {canMeet && (
          <button
            type="button"
            onClick={onOpenMeeting}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-electric/10 px-3 py-2 text-sm font-medium text-brand-electric transition-colors hover:bg-brand-electric/20"
          >
            <Radio className="h-4 w-4" aria-hidden />
            Open meeting view
          </button>
        )}
        {canReview && (
          <button
            type="button"
            onClick={onOpenReview}
            className="btn-primary inline-flex items-center gap-2 text-sm"
          >
            Review findings
          </button>
        )}
      </div>

      {/* Process button */}
      {session && (
        <div className="glass-card p-5">
          <ProcessButton
            sessionId={sessionId}
            status={session.status}
            coverage={questionnaire?.coverage ?? null}
            onDispatch={load}
          />
        </div>
      )}

      {/* Questions */}
      {loading ? (
        <p className="text-sm text-brand-silver">Loading questions…</p>
      ) : (
        <QuestionChecklist
          questions={questionnaire?.questions ?? []}
          version={questionnaire?.version ?? null}
        />
      )}

      {/* Recordings */}
      {(library.recordings.length > 0 || library.captures.length > 0) && (
        <div className="glass-card p-5">
          <h2 className="mb-3 text-sm font-semibold text-white">
            Recordings and captures
          </h2>
          <RecordingsLibrary
            sessionId={sessionId}
            recordings={library.recordings}
            captures={library.captures}
            canDelete={isAdmin}
            onDeleted={library.refresh}
          />
        </div>
      )}

      {/* Full transcript (T2) */}
      {transcriptClean && (
        <div className="glass-card p-5">
          <div className="mb-3 flex items-center gap-2">
            <FileText className="h-4 w-4 text-brand-electric" aria-hidden />
            <h2 className="text-sm font-semibold text-white">
              Full Transcript
            </h2>
          </div>
          <div className="max-h-[500px] overflow-y-auto rounded-lg bg-white/5 p-4">
            {transcriptClean.split('\n').map((line, i) => {
              if (!line.trim()) return <br key={i} />;
              const colonIdx = line.indexOf(':');
              if (colonIdx > 0 && colonIdx < 60) {
                const speaker = line.slice(0, colonIdx);
                const text = line.slice(colonIdx + 1);
                return (
                  <p key={i} className="mb-2 text-sm">
                    <span className="font-medium text-brand-electric">
                      {speaker}:
                    </span>
                    <span className="text-brand-silver">{text}</span>
                  </p>
                );
              }
              return (
                <p key={i} className="mb-2 text-sm text-brand-silver">
                  {line}
                </p>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
