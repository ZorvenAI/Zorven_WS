'use client';

import { useState } from 'react';
import { Check, X, Bookmark, Loader2, Lock } from 'lucide-react';
import {
  applyLearning,
  dismissLearning,
  saveLearning,
  type LearningRecord,
} from '@/lib/intelligence';

interface Props {
  learning: LearningRecord;
  canEdit: boolean;
  onChange?: (updated: LearningRecord) => void;
}

const IMPACT_COLOR: Record<string, string> = {
  HIGH: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  MEDIUM: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  LOW: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
};

const STATUS_COLOR: Record<string, string> = {
  new: 'text-brand-electric',
  applied: 'text-emerald-400',
  dismissed: 'text-slate-500',
  saved: 'text-sky-400',
  expired: 'text-slate-600',
};

export default function LearningCard({ learning, canEdit, onChange }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState(learning);

  const isWF2 = current.target_workflow === 'WF2';
  const terminal =
    current.status === 'applied' ||
    current.status === 'dismissed' ||
    current.status === 'expired';

  async function run(action: 'apply' | 'dismiss' | 'save') {
    setBusy(action);
    setError(null);
    try {
      if (action === 'apply') {
        await applyLearning(current.learning_id);
        const updated = { ...current, status: 'applied' as const };
        setCurrent(updated);
        onChange?.(updated);
      } else if (action === 'dismiss') {
        const updated = await dismissLearning(current.learning_id);
        setCurrent(updated);
        onChange?.(updated);
      } else {
        const updated = await saveLearning(current.learning_id);
        setCurrent(updated);
        onChange?.(updated);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="glass-card p-4 rounded-lg border border-white/5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span className="text-xs font-mono text-brand-silver uppercase tracking-wide">
              {current.category}
            </span>
            <span
              className={`text-xs px-2 py-0.5 rounded border ${
                IMPACT_COLOR[current.impact] ?? IMPACT_COLOR.LOW
              }`}
            >
              {current.impact}
            </span>
            <span className="text-xs text-brand-silver">
              {current.target_workflow} · {current.target_agent}
            </span>
            <span
              className={`text-xs font-semibold ${
                STATUS_COLOR[current.status] ?? 'text-brand-silver'
              }`}
            >
              {current.status}
            </span>
          </div>
          <p className="text-sm text-white font-medium leading-snug">
            {current.headline}
          </p>
        </div>
        <div className="flex flex-col items-end shrink-0">
          <span className="text-2xl font-heading font-bold text-brand-electric leading-none">
            {current.confidence}
          </span>
          <span className="text-[10px] text-brand-silver uppercase tracking-wider">
            confidence
          </span>
        </div>
      </div>

      {error && (
        <p className="mt-2 text-xs text-rose-400">{error}</p>
      )}

      {canEdit && !terminal && (
        <div className="mt-3 flex items-center gap-2">
          {isWF2 ? (
            <span className="flex items-center gap-1.5 text-xs text-amber-300">
              <Lock className="h-3 w-3" /> Requires admin approval
            </span>
          ) : (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => run('apply')}
              className="btn-primary text-xs px-3 py-1.5 inline-flex items-center gap-1.5 disabled:opacity-50"
            >
              {busy === 'apply' ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Check className="h-3 w-3" />
              )}
              Apply
            </button>
          )}
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run('save')}
            className="text-xs px-3 py-1.5 inline-flex items-center gap-1.5 rounded border border-white/10 text-brand-silver hover:text-white hover:bg-white/5 disabled:opacity-50"
          >
            {busy === 'save' ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Bookmark className="h-3 w-3" />
            )}
            Save
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run('dismiss')}
            className="text-xs px-3 py-1.5 inline-flex items-center gap-1.5 rounded border border-white/10 text-brand-silver hover:text-white hover:bg-white/5 disabled:opacity-50"
          >
            {busy === 'dismiss' ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <X className="h-3 w-3" />
            )}
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
