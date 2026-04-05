/**
 * ThoughtTrace — Visualises per-agent progress for an analysis job.
 *
 * Renders a vertical stepper showing each agent node's status
 * (pending → running → done / failed), plus an overall progress bar.
 * Parallel nodes (same started_at timestamp or multiple running) are
 * grouped side-by-side to indicate concurrent execution.
 */

'use client';

import type { AgentProgress, JobStatus } from '@/types/orchestration';
import {
  CheckCircle2,
  Circle,
  Clock,
  Loader2,
  XCircle,
  GitBranch,
} from 'lucide-react';

interface ThoughtTraceProps {
  progress: Record<string, AgentProgress>;
  /** Current overall job status. */
  jobStatus: JobStatus;
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
  awaiting_approval: <Clock className="w-5 h-5 text-amber-400" />,
};

const STATUS_LABEL: Record<AgentProgress['status'], string> = {
  pending: 'Waiting',
  running: 'Running…',
  done: 'Done',
  failed: 'Failed',
  awaiting_approval: 'Awaiting Approval',
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
    (p) => p.status === 'done' || p.status === 'failed' || p.status === 'awaiting_approval',
  ).length;
  return Math.round((done / entries.length) * 100);
}

/** Group entries into execution levels. Nodes with the same started_at
 *  are in the same parallel level. Nodes without started_at (pending)
 *  are grouped together at the end. */
function groupIntoLevels(
  entries: Array<[string, AgentProgress]>,
): Array<Array<[string, AgentProgress]>> {
  if (entries.length <= 1) return entries.length ? [entries] : [];

  const levels: Array<Array<[string, AgentProgress]>> = [];
  const pending: Array<[string, AgentProgress]> = [];

  // Group by started_at timestamp
  const byTimestamp = new Map<string, Array<[string, AgentProgress]>>();
  const order: string[] = [];

  for (const entry of entries) {
    const [, agent] = entry;
    const ts = agent.started_at;
    if (!ts) {
      pending.push(entry);
      continue;
    }
    if (!byTimestamp.has(ts)) {
      byTimestamp.set(ts, []);
      order.push(ts);
    }
    byTimestamp.get(ts)!.push(entry);
  }

  // Sort by timestamp ascending
  order.sort();
  for (const ts of order) {
    levels.push(byTimestamp.get(ts)!);
  }

  // Pending nodes at the end
  if (pending.length > 0) {
    levels.push(pending);
  }

  return levels;
}

export default function ThoughtTrace({
  progress,
  jobStatus,
  lastThought,
  progressPercent,
}: ThoughtTraceProps) {
  const entries = Object.entries(progress);
  const percent = progressPercent ?? calcPercent(progress);

  if (entries.length === 0 && (jobStatus === 'queued' || jobStatus === 'running')) {
    return (
      <div className="glass-card p-6">
        <h3 className="text-sm font-heading font-semibold text-white mb-4">
          Pipeline Progress
        </h3>
        <p className="text-sm text-brand-silver/60">
          {jobStatus === 'running'
            ? 'Initializing pipeline agents…'
            : 'Waiting for the pipeline to start…'}
        </p>
      </div>
    );
  }

  const levels = groupIntoLevels(entries);

  return (
    <div className="glass-card p-6">
      <h3 className="text-sm font-heading font-semibold text-white mb-4">
        Pipeline Progress
      </h3>

      {/* Agent steps grouped by execution level */}
      <div className="space-y-3 mb-5">
        {levels.map((level, levelIdx) => {
          const isParallel = level.length > 1;

          if (!isParallel) {
            // Single-node level — render as before
            const [nodeId, agent] = level[0];
            return (
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
                {agent.status === 'running' && lastThought && (
                  <p className="ml-8 mt-1 text-xs italic text-slate-400">
                    {lastThought}
                  </p>
                )}
              </div>
            );
          }

          // Multi-node parallel level
          return (
            <div key={`level-${levelIdx}`}>
              {/* Parallel indicator */}
              <div className="flex items-center gap-2 mb-2 ml-1">
                <GitBranch className="w-3.5 h-3.5 text-brand-teal rotate-180" />
                <span className="text-xs font-medium text-brand-teal">
                  Parallel
                </span>
                <div className="flex-1 h-px bg-brand-teal/20" />
              </div>

              {/* Side-by-side grid for parallel nodes */}
              <div className="grid grid-cols-2 gap-2 pl-2 border-l-2 border-brand-teal/30">
                {level.map(([nodeId, agent]) => (
                  <div key={nodeId}>
                    <div className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2.5">
                      {STATUS_ICON[agent.status]}
                      <span className="flex-1 text-sm font-medium text-brand-silver truncate">
                        {humanLabel(nodeId)}
                      </span>
                      <span className="text-xs text-brand-silver/60 whitespace-nowrap">
                        {STATUS_LABEL[agent.status]}
                      </span>
                    </div>
                    {agent.status === 'running' && lastThought && (
                      <p className="ml-7 mt-1 text-xs italic text-slate-400">
                        {lastThought}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
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
