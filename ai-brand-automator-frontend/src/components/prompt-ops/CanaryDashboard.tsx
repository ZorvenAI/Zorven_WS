'use client';

import { useEffect, useState } from 'react';
import {
  FlaskConical,
  Activity,
  History,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Zap,
  Play,
  Loader2,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type {
  CanaryDeployment,
  CanaryHistoryEntry,
  CanaryMetricsComparison,
  OptimizationRun,
} from '@/types/prompt-ops';
import {
  getActiveCanaries,
  getCanaryHistory,
  getCanaryMetrics,
  getOptimizationRuns,
  triggerOptimization,
} from '@/lib/prompt-ops';

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    healthy: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    regressed: 'bg-red-500/10 text-red-400 border-red-500/20',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colors[status] || colors.healthy}`}
    >
      {status}
    </span>
  );
}

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
    <span className={`inline-flex items-center gap-1 ${color} text-xs font-medium`}>
      {icon}
      {outcome.replace('_', ' ')}
    </span>
  );
}

function RunStateBadge({ state }: { state: string }) {
  const colors: Record<string, string> = {
    QUEUED: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    ACQUIRING_LOCK: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    LOADING_DATA: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    OPTIMIZING: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
    VALIDATING: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    CANARY: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    PRODUCTION: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
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

function RegressionIndicator({ value }: { value: number | null }) {
  if (value === null) return <span className="text-brand-silver/50 text-sm">--</span>;
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

export default function CanaryDashboard() {
  const [canaries, setCanaries] = useState<CanaryDeployment[]>([]);
  const [history, setHistory] = useState<CanaryHistoryEntry[]>([]);
  const [comparisons, setComparisons] = useState<Record<string, CanaryMetricsComparison>>({});
  const [optimizationRuns, setOptimizationRuns] = useState<OptimizationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  const handleTriggerOptimization = async (groupName: string) => {
    try {
      setTriggering(true);
      await triggerOptimization(groupName);
      // Refresh runs after a short delay
      setTimeout(async () => {
        try {
          const runs = await getOptimizationRuns();
          setOptimizationRuns(runs);
        } catch {
          // ignore refresh errors
        }
        setTriggering(false);
      }, 2000);
    } catch {
      setTriggering(false);
    }
  };

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        setError(null);

        const [activeCanaries, canaryHistory, runs] = await Promise.all([
          getActiveCanaries(),
          getCanaryHistory(),
          getOptimizationRuns().catch(() => [] as OptimizationRun[]),
        ]);

        setOptimizationRuns(runs);

        setCanaries(activeCanaries);
        setHistory(canaryHistory);

        // Fetch metrics for each active canary
        const metricsMap: Record<string, CanaryMetricsComparison> = {};
        await Promise.all(
          activeCanaries.map(async (c) => {
            try {
              const metrics = await getCanaryMetrics(c.prompt_name);
              metricsMap[c.prompt_name] = metrics;
            } catch {
              // Skip metrics that fail to load
            }
          })
        );
        setComparisons(metricsMap);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load canary data');
        setCanaries([]);
        setHistory([]);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card p-8 text-center">
        <AlertTriangle className="h-10 w-10 text-amber-400 mx-auto mb-3" />
        <p className="text-brand-silver text-sm">{error}</p>
        <p className="text-brand-silver/50 text-xs mt-2">
          Ensure prompt-optimization-svc is running and accessible
        </p>
      </div>
    );
  }

  // KPI cards
  const totalActive = canaries.length;
  const totalOptRuns = optimizationRuns.length;
  const totalSuccessful = optimizationRuns.filter((r) => r.state === 'CANARY' || r.state === 'PRODUCTION').length;
  const totalFailed = optimizationRuns.filter((r) => r.state === 'FAILED' || r.state === 'REJECTED').length;
  const totalPromoted = history.filter((h) => h.outcome === 'promoted').length;
  const totalRolledBack = history.filter((h) => h.outcome === 'rolled_back').length;
  const avgRegression =
    canaries.length > 0
      ? Object.values(comparisons).reduce(
          (sum, c) => sum + (c.regression_pct ?? 0),
          0
        ) / Math.max(Object.values(comparisons).length, 1)
      : null;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <Zap className="w-4 h-4 text-brand-electric" />
            <span className="text-xs text-brand-silver">Total Runs</span>
          </div>
          <p className="text-2xl font-heading font-bold text-white">{totalOptRuns}</p>
        </div>
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs text-brand-silver">Successful</span>
          </div>
          <p className="text-2xl font-heading font-bold text-white">{totalSuccessful}</p>
        </div>
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <XCircle className="w-4 h-4 text-red-400" />
            <span className="text-xs text-brand-silver">Failed</span>
          </div>
          <p className="text-2xl font-heading font-bold text-white">{totalFailed}</p>
        </div>
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="w-4 h-4 text-brand-electric" />
            <span className="text-xs text-brand-silver">Active Canaries</span>
          </div>
          <p className="text-2xl font-heading font-bold text-white">{totalActive}</p>
        </div>
        <div className="glass-card p-4">
          <div className="flex items-center gap-2 mb-1">
            <Activity className="w-4 h-4 text-brand-electric" />
            <span className="text-xs text-brand-silver">Promoted (30d)</span>
          </div>
          <p className="text-2xl font-heading font-bold text-white">{totalPromoted}</p>
        </div>
      </div>

      {/* Active Canaries Table */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <FlaskConical className="w-5 h-5 text-brand-electric" />
          <h2 className="text-lg font-heading font-bold text-white">
            Active Canary Deployments
          </h2>
        </div>
        {canaries.length === 0 ? (
          <p className="text-brand-silver/50 text-sm text-center py-6">
            No active canary deployments
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-brand-silver/70 border-b border-white/5">
                  <th className="pb-3 font-medium">Prompt</th>
                  <th className="pb-3 font-medium">Agent</th>
                  <th className="pb-3 font-medium">Canary</th>
                  <th className="pb-3 font-medium">Production</th>
                  <th className="pb-3 font-medium">Time Left</th>
                  <th className="pb-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {canaries.map((c) => (
                  <tr key={c.prompt_name} className="text-brand-silver">
                    <td className="py-3 text-white font-medium">{c.prompt_name}</td>
                    <td className="py-3">{c.agent_code}</td>
                    <td className="py-3">v{c.canary_version}</td>
                    <td className="py-3">v{c.production_version}</td>
                    <td className="py-3">
                      <span className="inline-flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5" />
                        {c.time_remaining_hours.toFixed(1)}h
                      </span>
                    </td>
                    <td className="py-3">
                      <StatusBadge
                        status={comparisons[c.prompt_name]?.status || 'healthy'}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Metrics Comparison Charts */}
      {Object.keys(comparisons).length > 0 && (
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-5 h-5 text-brand-electric" />
            <h2 className="text-lg font-heading font-bold text-white">
              Metrics Comparison
            </h2>
          </div>
          <div className="space-y-6">
            {Object.entries(comparisons).map(([promptName, comp]) => {
              const scorerNames = [
                ...new Set([
                  ...Object.keys(comp.canary_metrics),
                  ...Object.keys(comp.production_metrics),
                ]),
              ];
              const chartData = scorerNames.map((scorer) => ({
                scorer,
                canary: comp.canary_metrics[scorer] ?? 0,
                production: comp.production_metrics[scorer] ?? 0,
              }));

              return (
                <div key={promptName}>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-medium text-white">{promptName}</h3>
                    <div className="flex items-center gap-2">
                      <RegressionIndicator value={comp.regression_pct} />
                      <StatusBadge status={comp.status} />
                    </div>
                  </div>
                  {chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={chartData} barGap={4}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                        <XAxis
                          dataKey="scorer"
                          tick={{ fill: '#94a3b8', fontSize: 11 }}
                          axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                        />
                        <YAxis
                          domain={[0, 1]}
                          tick={{ fill: '#94a3b8', fontSize: 11 }}
                          axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#1e293b',
                            border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: '8px',
                            color: '#e2e8f0',
                          }}
                        />
                        <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
                        <Bar dataKey="production" fill="#3b82f6" name="Production" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="canary" fill="#8b5cf6" name="Canary" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-brand-silver/50 text-xs text-center py-4">
                      No metrics recorded yet
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Optimization Runs Table */}
      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-brand-electric" />
            <h2 className="text-lg font-heading font-bold text-white">
              Optimization Runs
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {(['wf1-discovery-pipeline', 'wf2-brand-strategy-pipeline', 'wf3-creative-pipeline'] as const).map(
              (group) => (
                <button
                  key={group}
                  onClick={() => handleTriggerOptimization(group)}
                  disabled={triggering}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-electric/10 text-brand-electric text-xs font-medium hover:bg-brand-electric/20 transition-colors disabled:opacity-50"
                >
                  {triggering ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Play className="w-3 h-3" />
                  )}
                  {group.replace('-pipeline', '').replace('wf', 'WF').replace('-', ' ').replace('discovery', 'Discovery').replace('brand strategy', 'Brand Strategy').replace('creative', 'Creative')}
                </button>
              )
            )}
          </div>
        </div>
        {optimizationRuns.length === 0 ? (
          <p className="text-brand-silver/50 text-sm text-center py-6">
            No optimization runs yet
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-brand-silver/70 border-b border-white/5">
                  <th className="pb-3 font-medium">Run ID</th>
                  <th className="pb-3 font-medium">Prompt</th>
                  <th className="pb-3 font-medium">Agent</th>
                  <th className="pb-3 font-medium">State</th>
                  <th className="pb-3 font-medium">Score</th>
                  <th className="pb-3 font-medium">Cost</th>
                  <th className="pb-3 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {optimizationRuns.map((run) => (
                  <tr key={run.run_id} className="text-brand-silver">
                    <td className="py-3 font-mono text-xs">{run.run_id.slice(0, 8)}</td>
                    <td className="py-3 text-white font-medium text-xs">{run.prompt_name}</td>
                    <td className="py-3">{run.agent_code}</td>
                    <td className="py-3">
                      <RunStateBadge state={run.state} />
                    </td>
                    <td className="py-3">
                      {run.score_after !== null ? run.score_after.toFixed(3) : '--'}
                    </td>
                    <td className="py-3">
                      {run.cost_usd !== null ? `$${run.cost_usd.toFixed(2)}` : '--'}
                    </td>
                    <td className="py-3 text-xs">
                      {new Date(run.updated_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* History Table */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <History className="w-5 h-5 text-brand-electric" />
          <h2 className="text-lg font-heading font-bold text-white">
            Canary History
          </h2>
        </div>
        {history.length === 0 ? (
          <p className="text-brand-silver/50 text-sm text-center py-6">
            No canary deployment history
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-brand-silver/70 border-b border-white/5">
                  <th className="pb-3 font-medium">Prompt</th>
                  <th className="pb-3 font-medium">Version</th>
                  <th className="pb-3 font-medium">Started</th>
                  <th className="pb-3 font-medium">Ended</th>
                  <th className="pb-3 font-medium">Outcome</th>
                  <th className="pb-3 font-medium">Regression</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {history.map((h, idx) => (
                  <tr key={`${h.prompt_name}-${h.canary_version}-${idx}`} className="text-brand-silver">
                    <td className="py-3 text-white font-medium">{h.prompt_name}</td>
                    <td className="py-3">v{h.canary_version}</td>
                    <td className="py-3">{new Date(h.started_at).toLocaleDateString()}</td>
                    <td className="py-3">{new Date(h.ended_at).toLocaleDateString()}</td>
                    <td className="py-3">
                      <OutcomeBadge outcome={h.outcome} />
                    </td>
                    <td className="py-3">
                      <RegressionIndicator value={h.final_regression_pct} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
