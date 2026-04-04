/**
 * StatusBadge — inline pill showing job status with colour coding.
 */

'use client';

import type { JobStatus } from '@/types/orchestration';

const CONFIG: Record<JobStatus, { bg: string; text: string; label: string }> = {
  queued: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', label: 'Queued' },
  running: { bg: 'bg-brand-electric/20', text: 'text-brand-electric', label: 'Running' },
  completed: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', label: 'Completed' },
  failed: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'Failed' },
  awaiting_approval: { bg: 'bg-amber-500/20', text: 'text-amber-400', label: 'Awaiting Approval' },
};

export default function StatusBadge({ status }: { status: JobStatus }) {
  const c = CONFIG[status];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${c.bg} ${c.text}`}
    >
      {c.label}
    </span>
  );
}
