'use client';

/**
 * J-01 — Process button with coverage warning.
 *
 * Enabled in GATHERED; disabled with reason in earlier states.
 * If coverage has shortfalls, a warning modal appears before dispatch.
 */

import { useState, useCallback } from 'react';
import { Play, Loader2, CheckCircle, AlertTriangle } from 'lucide-react';

import {
  triggerProcess,
  type SessionStatus,
  type QuestionnaireDetail,
  type WorkflowTarget,
} from '@/lib/onboarding-sessions';

const COVERAGE_THRESHOLD = 0.6;

interface ProcessButtonProps {
  sessionId: string;
  status: SessionStatus;
  coverage: Record<WorkflowTarget, number> | null;
  onDispatch?: () => void;
}

function disabledReason(status: SessionStatus): string | null {
  switch (status) {
    case 'DRAFT':
    case 'PREPARING':
    case 'READY':
      return 'Complete the meeting before processing';
    case 'MEETING_LIVE':
      return 'End the meeting to process';
    case 'PROCESSING':
      return 'Already processing';
    case 'REVIEW_PENDING':
    case 'CONFIRMED':
      return null; // re-run allowed
    case 'COMPLETED':
    case 'ARCHIVED':
      return 'Session is closed';
    case 'ESCALATED':
      return 'Resolve escalation first';
    default:
      return null;
  }
}

function hasCoverageShortfall(
  coverage: Record<WorkflowTarget, number> | null,
): boolean {
  if (!coverage) return false;
  return Object.values(coverage).some((v) => v < COVERAGE_THRESHOLD);
}

export default function ProcessButton({
  sessionId,
  status,
  coverage,
  onDispatch,
}: ProcessButtonProps) {
  const [dispatching, setDispatching] = useState(false);
  const [showWarning, setShowWarning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enabled = status === 'GATHERED' || status === 'REVIEW_PENDING' || status === 'CONFIRMED';
  const reason = disabledReason(status);

  const dispatch = useCallback(async () => {
    setDispatching(true);
    setError(null);
    try {
      await triggerProcess(sessionId);
      onDispatch?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Dispatch failed');
    } finally {
      setDispatching(false);
    }
  }, [sessionId, onDispatch]);

  const handleClick = useCallback(() => {
    if (hasCoverageShortfall(coverage)) {
      setShowWarning(true);
    } else {
      void dispatch();
    }
  }, [coverage, dispatch]);

  if (status === 'PROCESSING') {
    return (
      <div className="flex items-center gap-2 text-sm text-brand-electric">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Processing onboarding data…
      </div>
    );
  }

  if (status === 'REVIEW_PENDING') {
    return (
      <div className="flex items-center gap-2 text-sm text-green-400">
        <CheckCircle className="h-4 w-4" aria-hidden />
        Processing complete — ready for review
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-3">
        <button
          onClick={handleClick}
          disabled={!enabled || dispatching}
          className="btn-primary inline-flex items-center gap-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          title={reason ?? undefined}
        >
          {dispatching ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Play className="h-4 w-4" aria-hidden />
          )}
          Process onboarding data
        </button>
        {reason && (
          <span className="text-xs text-brand-silver">{reason}</span>
        )}
        {error && (
          <span className="text-xs text-red-400">{error}</span>
        )}
      </div>

      {showWarning && coverage && (
        <CoverageWarningModal
          coverage={coverage}
          onContinue={() => {
            setShowWarning(false);
            void dispatch();
          }}
          onCancel={() => setShowWarning(false)}
        />
      )}
    </>
  );
}

// ── Inline coverage warning modal ───────────────────────────────────

interface CoverageWarningModalProps {
  coverage: Record<WorkflowTarget, number>;
  onContinue: () => void;
  onCancel: () => void;
}

const WF_LABELS: Record<WorkflowTarget, string> = {
  WF1: 'Research & Discovery',
  WF2: 'Brand Identity',
  WF3: 'Campaign & Ads',
};

function CoverageWarningModal({
  coverage,
  onContinue,
  onCancel,
}: CoverageWarningModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      role="dialog"
      aria-modal="true"
      aria-label="Coverage shortfall warning"
    >
      <div className="glass-card w-full max-w-md p-6 space-y-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-yellow-400 shrink-0 mt-0.5" aria-hidden />
          <div>
            <h3 className="text-sm font-semibold text-white">
              Some areas have low coverage
            </h3>
            <p className="mt-1 text-xs text-brand-silver">
              Processing will proceed, but results may be less complete in
              thin areas. You can return to capture more evidence first.
            </p>
          </div>
        </div>

        <div className="space-y-2">
          {(Object.entries(coverage) as [WorkflowTarget, number][]).map(
            ([wf, score]) => (
              <div key={wf} className="flex items-center gap-3">
                <span className="text-xs text-brand-silver w-36 shrink-0">
                  {WF_LABELS[wf] ?? wf}
                </span>
                <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      score >= COVERAGE_THRESHOLD ? 'bg-green-500' : 'bg-yellow-400'
                    }`}
                    style={{ width: `${Math.round(score * 100)}%` }}
                  />
                </div>
                <span className="text-xs text-brand-silver w-10 text-right">
                  {Math.round(score * 100)}%
                </span>
              </div>
            ),
          )}
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onCancel}
            className="text-sm text-brand-silver hover:text-white"
          >
            Return to capture
          </button>
          <button
            onClick={onContinue}
            className="btn-primary text-sm"
          >
            Continue anyway
          </button>
        </div>
      </div>
    </div>
  );
}
