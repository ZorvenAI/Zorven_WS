/**
 * /dashboard/analysis/[job_id] — Dedicated ISO valuation detail view.
 *
 * Shows a focused brand equity report for a completed analysis job:
 * - NPV valuation top bar
 * - BSI gauge + NPV chart + Radar chart grid
 * - Findings, recommendations, and grounding citations
 *
 * Reuses usePollingJob and BrandEquityDashboard from existing infrastructure.
 */

'use client';

import { use } from 'react';
import Link from 'next/link';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { usePollingJob } from '@/hooks/usePollingJob';
import StatusBadge from '@/components/pipelines/StatusBadge';
import BrandEquityDashboard from '@/components/pipelines/BrandEquityDashboard';

interface PageProps {
  params: Promise<{ job_id: string }>;
}

export default function AnalysisDetailPage({ params }: PageProps) {
  useAuth();
  const { job_id: jobId } = use(params);

  const { job, isLoading, error } = usePollingJob(jobId);

  return (
    <div className="min-h-screen bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />

      <div className="relative z-10 max-w-5xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        {/* Back link */}
        <Link
          href="/dashboard/analysis"
          className="inline-flex items-center text-sm text-brand-silver/70 hover:text-brand-electric mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back to Reports
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
            <Link
              href="/dashboard/analysis"
              className="btn-outline text-sm px-4 py-2"
            >
              Back to Reports
            </Link>
          </div>
        )}

        {job && (
          <>
            {/* Header */}
            <div className="mb-8">
              <div className="flex items-center gap-3">
                <h1 className="font-heading text-xl font-heading font-bold text-white">
                  {job.manifest_name ?? 'Brand Analysis'}
                </h1>
                <StatusBadge status={job.status} />
              </div>
              <p className="mt-1 text-sm text-brand-silver/50">
                {job.input_prompt}
              </p>
              <div className="mt-2 flex items-center gap-4 text-xs text-brand-silver/40">
                <span>
                  Created {new Date(job.created_at).toLocaleString()}
                </span>
                {job.duration_seconds !== null && (
                  <span>Duration: {job.duration_seconds.toFixed(1)}s</span>
                )}
              </div>
            </div>

            {/* Completed: show full brand equity dashboard */}
            {job.status === 'completed' && job.result_data && (
              <BrandEquityDashboard resultData={job.result_data} />
            )}

            {/* Still running */}
            {(job.status === 'queued' || job.status === 'running') && (
              <div className="glass-card p-12 text-center">
                <Loader2 className="w-8 h-8 animate-spin text-brand-electric mx-auto mb-4" />
                <p className="text-brand-silver/60">
                  Analysis in progress&hellip;
                </p>
                <Link
                  href={`/dashboard/pipelines/${job.job_id}`}
                  className="text-sm text-brand-electric hover:underline mt-2 inline-block"
                >
                  View pipeline progress
                </Link>
              </div>
            )}

            {/* Failed */}
            {job.status === 'failed' && (
              <div className="glass-card p-6 border-red-500/30">
                <h3 className="font-heading text-sm font-heading font-semibold text-red-400 mb-2">
                  Analysis Failed
                </h3>
                <p className="text-sm text-brand-silver">
                  {job.error_message || 'An unknown error occurred.'}
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
