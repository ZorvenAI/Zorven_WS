/**
 * /dashboard/analysis — Historical brand equity reports list.
 *
 * Filters completed analysis jobs to show only brand equity / ISO
 * pipeline results. Links to the dedicated ISO detail view.
 */

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { RefreshCw } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { listJobs } from '@/lib/orchestration';
import type { AnalysisJob } from '@/types/orchestration';
import StatusBadge from '@/components/pipelines/StatusBadge';
import { formatCompact } from '@/lib/utils/iso-formatters';

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

/** Check if a job is a brand-equity / ISO valuation result. */
function isBrandEquityJob(job: AnalysisJob): boolean {
  if (job.status !== 'completed' || !job.result_data) return false;
  // Has a BSI score or valuation data
  return (
    typeof job.result_data.score === 'number' ||
    typeof job.result_data.valuation === 'object'
  );
}

export default function AnalysisPage() {
  useAuth();

  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = async () => {
    setIsLoading(true);
    try {
      const data = await listJobs();
      const reports = data
        .filter(isBrandEquityJob)
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        );
      setJobs(reports);
      setError(null);
    } catch (err) {
      setJobs([]);
      setError(err instanceof Error ? err.message : 'Failed to load reports');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  return (
    <div className="min-h-screen bg-brand-midnight">
      <div className="fixed inset-0 aura-glow pointer-events-none opacity-30" />

      <div className="relative z-10 max-w-5xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        {/* Back link */}
        <Link
          href="/dashboard"
          className="inline-flex items-center text-sm text-brand-silver/70 hover:text-brand-electric mb-6 transition-colors"
        >
          <svg
            className="w-4 h-4 mr-1"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          Back to Dashboard
        </Link>

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-heading text-2xl font-heading font-bold text-white">
              Brand Equity Reports
            </h1>
            <p className="mt-1 text-sm text-brand-silver/60">
              Completed ISO 10668 brand valuations and analyses
            </p>
          </div>
          <button
            onClick={fetchJobs}
            className="btn-outline flex items-center gap-1.5 text-sm px-3 py-2"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="glass-card p-4 mb-6 border-red-500/30">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {/* Loading skeleton */}
        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="glass-card p-5 animate-pulse flex items-center gap-4"
              >
                <div className="h-4 w-32 rounded bg-white/10" />
                <div className="h-4 w-24 rounded bg-white/10" />
                <div className="flex-1" />
                <div className="h-4 w-16 rounded bg-white/10" />
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && jobs.length === 0 && !error && (
          <div className="glass-card p-12 text-center">
            <p className="text-brand-silver/60 mb-4">
              No completed brand equity reports yet.
            </p>
            <Link
              href="/dashboard/pipelines"
              className="btn-primary inline-flex items-center gap-2 text-sm px-4 py-2"
            >
              Run a new analysis
            </Link>
          </div>
        )}

        {/* Report list */}
        {!isLoading && jobs.length > 0 && (
          <div className="space-y-3">
            {jobs.map((job) => {
              const score =
                typeof job.result_data?.score === 'number'
                  ? Math.round(job.result_data.score as number)
                  : null;
              const valuation = job.result_data?.valuation as
                | { brand_value_npv?: number }
                | undefined;
              const npv = valuation?.brand_value_npv;

              return (
                <Link
                  key={job.job_id}
                  href={`/dashboard/analysis/${job.job_id}`}
                  className="glass-card p-5 flex items-center gap-4 hover:border-brand-electric/30 transition-colors cursor-pointer group"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-medium text-white truncate">
                        {job.manifest_name ?? 'Brand Analysis'}
                      </span>
                      <StatusBadge status={job.status} />
                    </div>
                    <p className="mt-1 text-xs text-brand-silver/50 truncate">
                      {job.input_prompt}
                    </p>
                  </div>

                  {/* BSI score */}
                  {score !== null && (
                    <div className="text-center">
                      <span className="text-xs text-brand-silver/40">BSI</span>
                      <p className="text-sm font-heading font-bold text-brand-electric">
                        {score}
                      </p>
                    </div>
                  )}

                  {/* NPV */}
                  {npv != null && (
                    <div className="text-center">
                      <span className="text-xs text-brand-silver/40">NPV</span>
                      <p className="text-sm font-heading font-bold text-brand-mint">
                        {formatCompact(npv)}
                      </p>
                    </div>
                  )}

                  <span className="text-xs text-brand-silver/40 whitespace-nowrap">
                    {timeAgo(job.created_at)}
                  </span>

                  <svg
                    className="w-4 h-4 text-brand-silver/30 group-hover:text-brand-electric transition-colors flex-shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
