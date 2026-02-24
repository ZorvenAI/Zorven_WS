/**
 * ThoughtTrace — Visualises per-agent progress for an analysis job.
 *
 * Renders a vertical stepper showing each agent node's status
 * (pending → running → done / failed), plus an overall progress bar.
 */

'use client';

import type { AgentProgress } from '@/types/orchestration';
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
} from 'lucide-react';

interface ThoughtTraceProps {
  progress: Record<string, AgentProgress>;
  /** Current overall job status. */
  jobStatus: 'queued' | 'running' | 'completed' | 'failed';
  /** Latest AI reasoning snippet from agent trace events. */
  lastThought?: string | null;
  /** Server-provided progress percent (overrides local calc when present). */
  progressPercent?: number;
}

const STATUS_ICON: Record<AgentProgress['status'], React.ReactNode> = {
  pending: <Circle className="w-5 h-5 text-brand-silver/40" />,
  running: <Loader2 className="w-5 h-5 text-brand-electric animate-spin" />,
  done: <CheckCircle2 className="w-5 h-5 text-emerald-400" />,
  failed: <XCircle className="w-5 h-5 text-red-400" />,
};

const STATUS_LABEL: Record<AgentProgress['status'], string> = {
  pending: 'Waiting',
  running: 'Running…',
  done: 'Done',
  failed: 'Failed',
};

function humanLabel(nodeId: string): string {
  return nodeId
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function calcPercent(progress: Record<string, AgentProgress>): number {
  const entries = Object.values(progress);
  if (entries.length === 0) return 0;
  const done = entries.filter(
    (p) => p.status === 'done' || p.status === 'failed',
  ).length;
  return Math.round((done / entries.length) * 100);
}

export default function ThoughtTrace({
  progress,
  jobStatus,
  lastThought,
  progressPercent,
}: ThoughtTraceProps) {
  const entries = Object.entries(progress);
  const percent = progressPercent ?? calcPercent(progress);

  if (entries.length === 0 && jobStatus === 'queued') {
    return (
      <div className="glass-card p-6">
        <h3 className="text-sm font-heading font-semibold text-white mb-4">
          Pipeline Progress
        </h3>
        <p className="text-sm text-brand-silver/60">
          Waiting for the pipeline to start…
        </p>
      </div>
    );
  }

  return (
    <div className="glass-card p-6">
      <h3 className="text-sm font-heading font-semibold text-white mb-4">
        Pipeline Progress
      </h3>

      {/* Agent steps */}
      <div className="space-y-3 mb-5">
        {entries.map(([nodeId, agent]) => (
          <div key={nodeId}>
            <div className="flex items-center gap-3 rounded-lg bg-white/5 px-4 py-2.5">
              {STATUS_ICON[agent.status]}
              <span className="flex-1 text-sm font-medium text-brand-silver">
                {humanLabel(nodeId)}
              </span>
              <span className="text-xs text-brand-silver/60">
                {STATUS_LABEL[agent.status]}
              </span>
            </div>
            {/* Show last_thought beneath the active (running) node */}
            {agent.status === 'running' && lastThought && (
              <p className="ml-8 mt-1 text-xs italic text-slate-400">
                {lastThought}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="h-2 w-full rounded-full bg-white/10 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-electric to-brand-teal transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-1.5 text-right text-xs text-brand-silver/50">
        {percent}%
      </p>
    </div>
  );
}
