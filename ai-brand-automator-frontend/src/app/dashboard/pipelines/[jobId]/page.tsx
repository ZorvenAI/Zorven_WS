/**
 * /dashboard/pipelines/[jobId] — Job detail page.
 *
 * Shows ThoughtTrace (progress stepper) while running and
 * ResultDashboard once completed.  Polls automatically.
 */

'use client';

import { use } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, XCircle, Loader2 } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { useTenantRole } from '@/hooks/useTenantRole';
import { usePollingJob } from '@/hooks/usePollingJob';
import { cancelJob } from '@/lib/orchestration';
import StatusBadge from '@/components/pipelines/StatusBadge';
import ThoughtTrace from '@/components/pipelines/ThoughtTrace';
import ResultDashboard from '@/components/pipelines/ResultDashboard';
import { useState } from 'react';

interface PageProps {
  params: Promise<{ jobId: string }>;
}

export default function JobDetailPage({ params }: PageProps) {
  useAuth();
  const { canEdit } = useTenantRole();
  const router = useRouter();
  const { jobId } = use(params);

  const { job, isLoading, error, refresh } = usePollingJob(jobId);
  const [cancelling, setCancelling] = useState(false);

  const handleCancel = async () => {
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
  };

  const isTerminal =
    job?.status === 'completed' || job?.status === 'failed';
  const canCancel =
    canEdit &&
    job &&
    (job.status === 'queued' || job.status === 'running');

  return (
    <div className="min-h-screen bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />

      <div className="relative z-10 max-w-4xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
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

              {canCancel && (
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

            {/* Progress stepper */}
            {!isTerminal && (
              <div className="mb-6">
                <ThoughtTrace
                  progress={job.progress}
                  jobStatus={job.status}
                />
              </div>
            )}

            {/* Completed: show progress summary + results */}
            {job.status === 'completed' && (
              <div className="space-y-6">
                <ThoughtTrace
                  progress={job.progress}
                  jobStatus={job.status}
                />
                {job.result_data && (
                  <ResultDashboard resultData={job.result_data} />
                )}
              </div>
            )}

            {/* Failed: show error */}
            {job.status === 'failed' && (
              <div className="space-y-6">
                <ThoughtTrace
                  progress={job.progress}
                  jobStatus={job.status}
                />
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
