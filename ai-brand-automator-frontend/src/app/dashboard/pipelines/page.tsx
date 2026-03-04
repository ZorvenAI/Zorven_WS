/**
 * /dashboard/pipelines — list of the user's analysis jobs
 * with a "New Analysis" button.
 */

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus, RefreshCw } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { listJobs } from '@/lib/orchestration';
import type { AnalysisJob } from '@/types/orchestration';
import StatusBadge from '@/components/pipelines/StatusBadge';
import NewAnalysisModal from '@/components/pipelines/NewAnalysisModal';

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

export default function PipelinesPage() {
  useAuth();
  const router = useRouter();

  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const fetchJobs = async () => {
    setIsLoading(true);
    try {
      const data = await listJobs();
      // Sort newest-first
      data.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
      setJobs(data);
      setError(null);
    } catch (err) {
      setJobs([]);
      setError(err instanceof Error ? err.message : 'Failed to load jobs');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  const handleCreated = (jobId: string) => {
    setModalOpen(false);
    router.push(`/dashboard/pipelines/${jobId}`);
  };

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
            <h1 className="text-2xl font-heading font-bold text-white">
              Analysis Pipelines
            </h1>
            <p className="mt-1 text-sm text-brand-silver/60">
              Run AI-powered brand analyses and view results
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchJobs}
              className="btn-outline flex items-center gap-1.5 text-sm px-3 py-2"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={() => setModalOpen(true)}
              className="btn-primary flex items-center gap-2 text-sm px-4 py-2"
            >
              <Plus className="w-4 h-4" />
              New Analysis
            </button>
          </div>
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
              No analysis jobs yet.
            </p>
            <button
              onClick={() => setModalOpen(true)}
              className="btn-primary inline-flex items-center gap-2 text-sm px-4 py-2"
            >
              <Plus className="w-4 h-4" />
              Start your first analysis
            </button>
          </div>
        )}

        {/* Job list */}
        {!isLoading && jobs.length > 0 && (
          <div className="space-y-3">
            {jobs.map((job) => (
              <Link
                key={job.job_id}
                href={`/dashboard/pipelines/${job.job_id}`}
                className="glass-card p-5 flex items-center gap-4 hover:border-brand-electric/30 transition-colors cursor-pointer group"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-white truncate">
                      {job.manifest_name ?? 'Auto-detect'}
                    </span>
                    <StatusBadge status={job.status} />
                  </div>
                  <p className="mt-1 text-xs text-brand-silver/50 truncate">
                    {job.input_prompt}
                  </p>
                </div>

                {job.duration_seconds !== null && (
                  <span className="text-xs text-brand-silver/40 whitespace-nowrap">
                    {job.duration_seconds.toFixed(0)}s
                  </span>
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
            ))}
          </div>
        )}
      </div>

      {/* New analysis modal */}
      <NewAnalysisModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={handleCreated}
      />
    </div>
  );
}
