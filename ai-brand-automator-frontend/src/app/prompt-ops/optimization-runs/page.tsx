'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  Zap,
  ArrowLeft,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import type { OptimizationRun } from '@/types/prompt-ops';
import { getOptimizationRuns } from '@/lib/prompt-ops';

function RunStateBadge({ state }: { state: string }) {
  const colors: Record<string, string> = {
    QUEUED: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    ACQUIRING_LOCK: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    LOADING_DATA: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    OPTIMIZING: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    VALIDATING: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    CANARY: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    PRODUCTION: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    COMPLETED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    PENDING_APPROVAL: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    FAILED: 'bg-red-500/10 text-red-400 border-red-500/20',
    REJECTED: 'bg-red-500/10 text-red-400 border-red-500/20',
    DEFERRED: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colors[state] || 'bg-gray-500/10 text-gray-400 border-gray-500/20'}`}
    >
      {state}
    </span>
  );
}

export default function OptimizationRunsPage() {
  useAuth();

  const [runs, setRuns] = useState<OptimizationRun[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMounted, setHasMounted] = useState(false);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  const loadPage = useCallback(async (p: number, size: number) => {
    try {
      setLoading(true);
      setError(null);
      const resp = await getOptimizationRuns(p, size);
      setRuns(resp.runs);
      setTotal(resp.total);
      setPage(resp.page);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to load optimization runs'
      );
      setRuns([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPage(1, pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!hasMounted) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric" />
      </div>
    );
  }

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="min-h-screen bg-brand-midnight p-6 lg:p-10">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <Link
              href="/prompt-ops"
              className="inline-flex items-center gap-1 text-brand-silver hover:text-white text-sm mb-2 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Prompt Operations
            </Link>
            <div className="flex items-center gap-3">
              <Zap className="w-6 h-6 text-brand-electric" />
              <div>
                <h1 className="text-2xl font-heading font-bold text-white">
                  Optimization Runs
                </h1>
                <p className="text-sm text-brand-silver mt-0.5">
                  Complete history of all GEPA optimization runs
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-brand-silver/70">Per page</label>
            <select
              value={pageSize}
              onChange={(e) => {
                const newSize = Number(e.target.value);
                setPageSize(newSize);
                setPage(1);
                loadPage(1, newSize);
              }}
              className="bg-white/5 border border-white/10 rounded-md px-2 py-1 text-xs text-brand-silver focus:outline-none focus:border-brand-electric/50"
            >
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n} className="bg-brand-midnight">
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="glass-card p-8 text-center">
            <AlertTriangle className="h-10 w-10 text-amber-400 mx-auto mb-3" />
            <p className="text-brand-silver text-sm">{error}</p>
          </div>
        )}

        {/* Table */}
        <div className="glass-card p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric" />
            </div>
          ) : runs.length === 0 ? (
            <p className="text-brand-silver/50 text-sm text-center py-12">
              No optimization runs yet
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-brand-silver/70 border-b border-white/5">
                      <th className="pb-3 font-medium">Run ID</th>
                      <th className="pb-3 font-medium">Prompt</th>
                      <th className="pb-3 font-medium">Agent</th>
                      <th className="pb-3 font-medium">State</th>
                      <th className="pb-3 font-medium">Score Before</th>
                      <th className="pb-3 font-medium">Score After</th>
                      <th className="pb-3 font-medium">Improvement</th>
                      <th className="pb-3 font-medium">Cost</th>
                      <th className="pb-3 font-medium">Updated</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {runs.map((run) => (
                      <tr key={run.run_id} className="text-brand-silver">
                        <td className="py-3 font-mono text-xs">
                          {run.run_id.slice(0, 8)}
                        </td>
                        <td className="py-3 text-white font-medium text-xs">
                          {run.prompt_name}
                        </td>
                        <td className="py-3">{run.agent_code}</td>
                        <td className="py-3">
                          <RunStateBadge state={run.state} />
                        </td>
                        <td className="py-3">
                          {run.score_before !== null
                            ? run.score_before.toFixed(3)
                            : '--'}
                        </td>
                        <td className="py-3">
                          {run.score_after !== null
                            ? run.score_after.toFixed(3)
                            : '--'}
                        </td>
                        <td className="py-3">
                          {run.improvement !== null ? (
                            <span
                              className={
                                run.improvement > 0
                                  ? 'text-emerald-400'
                                  : run.improvement < 0
                                    ? 'text-red-400'
                                    : 'text-brand-silver'
                              }
                            >
                              {run.improvement > 0 ? '+' : ''}
                              {(run.improvement * 100).toFixed(1)}%
                            </span>
                          ) : (
                            '--'
                          )}
                        </td>
                        <td className="py-3">
                          {run.cost_usd !== null
                            ? `$${run.cost_usd.toFixed(2)}`
                            : '--'}
                        </td>
                        <td className="py-3 text-xs">
                          {new Date(run.updated_at).toLocaleDateString()}{' '}
                          <span className="text-brand-silver/50 text-xs">
                            {new Date(run.updated_at).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination Controls */}
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-white/5">
                <span className="text-xs text-brand-silver/50">
                  Showing {(page - 1) * pageSize + 1}–
                  {Math.min(page * pageSize, total)} of {total} entries
                </span>
                <div className="flex items-center gap-1">
                  <button
                    disabled={page <= 1}
                    onClick={() => {
                      const p = page - 1;
                      setPage(p);
                      loadPage(p, pageSize);
                    }}
                    className="p-1.5 rounded-md hover:bg-white/5 text-brand-silver disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  {/* Page number buttons */}
                  {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                    let pageNum: number;
                    if (totalPages <= 7) {
                      pageNum = i + 1;
                    } else if (page <= 4) {
                      pageNum = i + 1;
                    } else if (page >= totalPages - 3) {
                      pageNum = totalPages - 6 + i;
                    } else {
                      pageNum = page - 3 + i;
                    }
                    return (
                      <button
                        key={pageNum}
                        onClick={() => {
                          setPage(pageNum);
                          loadPage(pageNum, pageSize);
                        }}
                        className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                          pageNum === page
                            ? 'bg-brand-electric/20 text-brand-electric'
                            : 'text-brand-silver hover:bg-white/5'
                        }`}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                  <button
                    disabled={page >= totalPages}
                    onClick={() => {
                      const p = page + 1;
                      setPage(p);
                      loadPage(p, pageSize);
                    }}
                    className="p-1.5 rounded-md hover:bg-white/5 text-brand-silver disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
