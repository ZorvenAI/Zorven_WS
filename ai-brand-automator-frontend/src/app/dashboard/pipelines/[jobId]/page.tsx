/**
 * /dashboard/pipelines/[jobId] — Job detail page.
 *
 * Shows PipelineGraph (React Flow DAG) when manifest data is available,
 * with ThoughtTrace as fallback.  LogConsole streams execution entries.
 * ResultDashboard renders final results (routes to BrandEquityDashboard
 * for brand equity manifests).  Polls automatically.
 */

'use client';

import { use, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, XCircle, Loader2 } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useTenantRole } from '@/hooks/useTenantRole';
import { usePollingJob } from '@/hooks/usePollingJob';
import { cancelJob, getManifestGraphData } from '@/lib/orchestration';
import StatusBadge from '@/components/pipelines/StatusBadge';
import ThoughtTrace from '@/components/pipelines/ThoughtTrace';
import ResultDashboard from '@/components/pipelines/ResultDashboard';
import PipelineGraph from '@/components/pipelines/PipelineGraph';
import LogConsole from '@/components/pipelines/LogConsole';
import type {
  AgentProgress,
  LogEntry,
  ManifestGraphData,
} from '@/types/orchestration';

interface PageProps {
  params: Promise<{ jobId: string }>;
}

/** Format a Date to HH:MM:SS for log entries. */
function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/** Diff progress snapshots to produce new log entries. */
function diffProgress(
  prev: Record<string, AgentProgress>,
  next: Record<string, AgentProgress>,
): LogEntry[] {
  const entries: LogEntry[] = [];
  const now = formatTime(new Date());

  for (const nodeId of Object.keys(next)) {
    const prevStatus = prev[nodeId]?.status;
    const nextStatus = next[nodeId]?.status;

    if (prevStatus === nextStatus) continue;

    if (nextStatus === 'running') {
      entries.push({
        timestamp: now,
        nodeId,
        message: 'Starting\u2026',
        level: 'info',
      });
    } else if (nextStatus === 'done') {
      entries.push({
        timestamp: now,
        nodeId,
        message: 'Completed',
        level: 'success',
      });
    } else if (nextStatus === 'failed') {
      entries.push({
        timestamp: now,
        nodeId,
        message: 'Failed',
        level: 'error',
      });
    }
  }

  return entries;
}

export default function JobDetailPage({ params }: PageProps) {
  useAuth();
  const { canEdit } = useTenantRole();
  const router = useRouter();
  const { jobId } = use(params);

  const { job, quickStatus, isLoading, error, refresh } = usePollingJob(jobId);
  const [cancelling, setCancelling] = useState(false);
  const [manifestData, setManifestData] = useState<ManifestGraphData | null>(
    null,
  );
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const prevProgressRef = useRef<Record<string, AgentProgress>>({});

  // Fetch manifest graph data when the job's manifest ID is known
  useEffect(() => {
    if (!job?.manifest) return;
    let cancelled = false;
    getManifestGraphData(job.manifest).then((data) => {
      if (!cancelled) setManifestData(data);
    });
    return () => {
      cancelled = true;
    };
  }, [job?.manifest]);

  // Generate log entries from progress diffs
  useEffect(() => {
    if (!job) return;
    const newEntries = diffProgress(prevProgressRef.current, job.progress);
    if (newEntries.length > 0) {
      setLogEntries((prev) => [...prev, ...newEntries]);
    }
    prevProgressRef.current = job.progress;
  }, [job?.progress]);

  const handleCancel = useCallback(async () => {
    if (!job) return;
    setCancelling(true);
    try {
      await cancelJob(job.job_id);
      refresh();
    } catch {
      // Best-effort — the job may already be terminal
    } finally {
      setCancelling(false);
    }
  }, [job, refresh]);

  const isTerminal =
    job?.status === 'completed' || job?.status === 'failed' || job?.status === 'awaiting_approval';
  const canCancelJob =
    canEdit &&
    job &&
    (job.status === 'queued' || job.status === 'running');

  return (
    <div className="min-h-screen bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />

      <div className="relative z-10 max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        {/* Back link */}
        <Link
          href="/dashboard/pipelines"
          className="inline-flex items-center text-sm text-brand-silver/70 hover:text-brand-electric mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back to Pipelines
        </Link>

        {/* Loading */}
        {isLoading && !job && (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="w-8 h-8 animate-spin text-brand-electric" />
          </div>
        )}

        {/* Error */}
        {error && !job && (
          <div className="glass-card p-6 border-red-500/30 text-center">
            <p className="text-red-400 mb-4">{error}</p>
            <button
              onClick={() => router.push('/dashboard/pipelines')}
              className="btn-outline text-sm px-4 py-2"
            >
              Back to Pipelines
            </button>
          </div>
        )}

        {job && (
          <>
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-xl font-heading font-bold text-white">
                    {job.manifest_name ?? 'Auto-detect Pipeline'}
                  </h1>
                  <StatusBadge status={job.status} />
                </div>
                <p className="mt-1 text-sm text-brand-silver/50">
                  {job.input_prompt}
                </p>
                <div className="mt-2 flex items-center gap-4 text-xs text-brand-silver/40">
                  <span>
                    Created{' '}
                    {new Date(job.created_at).toLocaleString()}
                  </span>
                  {job.duration_seconds !== null && (
                    <span>Duration: {job.duration_seconds.toFixed(1)}s</span>
                  )}
                </div>
              </div>

              {canCancelJob && (
                <button
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="btn-outline flex items-center gap-2 text-sm text-red-400 border-red-500/30 hover:bg-red-500/10 px-4 py-2"
                >
                  {cancelling ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <XCircle className="w-4 h-4" />
                  )}
                  Cancel
                </button>
              )}
            </div>

            {/* 2-column layout: Graph/Stepper (left) + Log Console (right) */}
            {!isTerminal && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                {/* Pipeline visualization — 2/3 width */}
                <div className="lg:col-span-2">
                  {manifestData ? (
                    <PipelineGraph
                      manifestData={manifestData}
                      progress={job.progress}
                    />
                  ) : (
                    <ThoughtTrace
                      progress={quickStatus?.progress ?? job.progress}
                      jobStatus={job.status}
                      lastThought={quickStatus?.last_thought}
                      progressPercent={quickStatus?.progress_percent}
                    />
                  )}
                </div>

                {/* Log console — 1/3 width */}
                <div className="lg:col-span-1">
                  <LogConsole entries={logEntries} />
                </div>
              </div>
            )}

            {/* Completed or awaiting approval: show graph summary + results */}
            {(job.status === 'completed' || job.status === 'awaiting_approval') && (
              <div className="space-y-6">
                {manifestData ? (
                  <PipelineGraph
                    manifestData={manifestData}
                    progress={job.progress}
                  />
                ) : (
                  <ThoughtTrace
                    progress={job.progress}
                    jobStatus={job.status}
                  />
                )}
                {logEntries.length > 0 && <LogConsole entries={logEntries} />}
                {job.result_data && (
                  <ResultDashboard
                    resultData={job.result_data}
                    manifestName={job.manifest_name}
                    jobId={job.job_id}
                    jobStatus={job.status}
                  />
                )}
              </div>
            )}

            {/* Failed: show error */}
            {job.status === 'failed' && (
              <div className="space-y-6">
                {manifestData ? (
                  <PipelineGraph
                    manifestData={manifestData}
                    progress={job.progress}
                  />
                ) : (
                  <ThoughtTrace
                    progress={job.progress}
                    jobStatus={job.status}
                  />
                )}
                {logEntries.length > 0 && <LogConsole entries={logEntries} />}
                <div className="glass-card p-6 border-red-500/30">
                  <h3 className="text-sm font-heading font-semibold text-red-400 mb-2">
                    Pipeline Failed
                  </h3>
                  <p className="text-sm text-brand-silver">
                    {job.error_message || 'An unknown error occurred.'}
                  </p>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
