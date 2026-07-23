'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  History,
  ArrowLeft,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import type { CanaryHistoryEntry } from '@/types/prompt-ops';
import { getCanaryHistory } from '@/lib/prompt-ops';

function OutcomeBadge({ outcome }: { outcome: string }) {
  const config: Record<string, { color: string; icon: React.ReactNode }> = {
    promoted: {
      color: 'text-emerald-400',
      icon: <CheckCircle2 className="w-3.5 h-3.5" />,
    },
    rolled_back: {
      color: 'text-red-400',
      icon: <XCircle className="w-3.5 h-3.5" />,
    },
    expired: {
      color: 'text-amber-400',
      icon: <AlertTriangle className="w-3.5 h-3.5" />,
    },
  };
  const { color, icon } = config[outcome] || config.expired;
  return (
    <span
      className={`inline-flex items-center gap-1 ${color} text-xs font-medium`}
    >
      {icon}
      {outcome.replace('_', ' ')}
    </span>
  );
}

function RegressionIndicator({ value }: { value: number | null }) {
  if (value === null)
    return <span className="text-brand-silver/50 text-sm">--</span>;
  const isPositive = value > 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-sm font-medium ${
        isPositive ? 'text-red-400' : 'text-emerald-400'
      }`}
    >
      {isPositive ? (
        <ArrowDownRight className="w-3.5 h-3.5" />
      ) : (
        <ArrowUpRight className="w-3.5 h-3.5" />
      )}
      {Math.abs(value * 100).toFixed(1)}%
    </span>
  );
}

export default function CanaryHistoryPage() {
  useAuth();

  const [history, setHistory] = useState<CanaryHistoryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMounted, setHasMounted] = useState(false);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  const loadPage = useCallback(
    async (p: number, size: number) => {
      try {
        setLoading(true);
        setError(null);
        const resp = await getCanaryHistory(p, size);
        setHistory(resp.history);
        setTotal(resp.total);
        setPage(resp.page);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Failed to load canary history'
        );
        setHistory([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    []
  );

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
              <History className="w-6 h-6 text-brand-electric" />
              <div>
                <h1 className="text-2xl font-heading font-bold text-white">
                  Canary Deployment History
                </h1>
                <p className="text-sm text-brand-silver mt-0.5">
                  Complete history of all canary deployments (last 30 days)
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
          ) : history.length === 0 ? (
            <p className="text-brand-silver/50 text-sm text-center py-12">
              No canary deployment history
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-brand-silver/70 border-b border-white/5">
                      <th className="pb-3 font-medium">Prompt</th>
                      <th className="pb-3 font-medium">Version</th>
                      <th className="pb-3 font-medium">Started</th>
                      <th className="pb-3 font-medium">Ended</th>
                      <th className="pb-3 font-medium">Duration</th>
                      <th className="pb-3 font-medium">Outcome</th>
                      <th className="pb-3 font-medium">Regression</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {history.map((h, idx) => {
                      const started = new Date(h.started_at);
                      const ended = new Date(h.ended_at);
                      const durationHrs = Math.round(
                        (ended.getTime() - started.getTime()) / 3600000
                      );
                      return (
                        <tr
                          key={`${h.prompt_name}-${h.canary_version}-${idx}`}
                          className="text-brand-silver"
                        >
                          <td className="py-3 text-white font-medium">
                            {h.prompt_name}
                          </td>
                          <td className="py-3">v{h.canary_version}</td>
                          <td className="py-3">
                            {started.toLocaleDateString()}{' '}
                            <span className="text-brand-silver/50 text-xs">
                              {started.toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                          </td>
                          <td className="py-3">
                            {ended.toLocaleDateString()}{' '}
                            <span className="text-brand-silver/50 text-xs">
                              {ended.toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                          </td>
                          <td className="py-3 text-xs">{durationHrs}h</td>
                          <td className="py-3">
                            <OutcomeBadge outcome={h.outcome} />
                          </td>
                          <td className="py-3">
                            <RegressionIndicator
                              value={h.final_regression_pct}
                            />
                          </td>
                        </tr>
                      );
                    })}
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
