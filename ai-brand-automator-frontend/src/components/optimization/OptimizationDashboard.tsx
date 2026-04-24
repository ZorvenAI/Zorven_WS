'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Activity, Zap } from 'lucide-react';
import type {
  CampaignRegistry,
  OptimizationRecommendation,
  OptimizationAction,
} from '@/types/optimization';
import {
  fetchCampaigns,
  fetchRecommendations,
  fetchActions,
  fetchAllActions,
  fetchAllRecommendations,
  fetchPerformanceTrend,
  triggerOptimizationTick,
} from '@/lib/optimization';
import type { PerformanceTrendPoint } from '@/lib/optimization';
import CampaignSelector from './CampaignSelector';
import CampaignMetricsCard from './CampaignMetricsCard';
import RecommendationsList from './RecommendationsList';
import RecentActionsList from './RecentActionsList';
import OptimizationSettings from './OptimizationSettings';
import CampaignPerformanceChart from './CampaignPerformanceChart';

const POLL_INTERVAL_MS = 30_000;

export default function OptimizationDashboard() {
  const [campaigns, setCampaigns] = useState<CampaignRegistry[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(
    null
  );
  const [recommendations, setRecommendations] = useState<
    OptimizationRecommendation[]
  >([]);
  const [actions, setActions] = useState<OptimizationAction[]>([]);
  const [trendData, setTrendData] = useState<PerformanceTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [trendLoading, setTrendLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState<{
    kind: 'info' | 'skipped' | 'completed' | 'error';
    title: string;
    reasons?: string[];
  } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selectedCampaign = campaigns.find(
    (c) => c.campaign_id === selectedCampaignId
  );

  // Load campaigns on mount
  const loadCampaigns = useCallback(async () => {
    try {
      const data = await fetchCampaigns();
      setCampaigns(data);
      if (data.length > 0 && !selectedCampaignId) {
        setSelectedCampaignId(data[0].campaign_id);
      }
    } catch (err) {
      setCampaigns([]);
      console.error('Failed to load campaigns:', err);
      setError('Failed to load campaigns');
    }
  }, [selectedCampaignId]);

  // Load campaign detail data — each call is independent so failures
  // are isolated (one failing endpoint doesn't blank out everything).
  const loadCampaignData = useCallback(async () => {
    if (!selectedCampaignId) return;

    // Fetch per-campaign + global data independently
    const [recsResult, actsResult, allActsResult, allRecsResult] =
      await Promise.allSettled([
        fetchRecommendations(selectedCampaignId, 'all'),
        fetchActions(selectedCampaignId),
        fetchAllActions(),
        fetchAllRecommendations('all'),
      ]);

    const recs =
      recsResult.status === 'fulfilled' ? recsResult.value : [];
    const acts =
      actsResult.status === 'fulfilled' ? actsResult.value : [];
    const allActs =
      allActsResult.status === 'fulfilled' ? allActsResult.value : [];
    const allRecs =
      allRecsResult.status === 'fulfilled' ? allRecsResult.value : [];

    // Use per-campaign recs if available, otherwise show global
    setRecommendations(recs.length > 0 ? recs : allRecs);

    // Merge per-campaign actions with global actions (deduplicated)
    const seenIds = new Set(acts.map((a) => a.action_id));
    const merged = [
      ...acts,
      ...allActs.filter((a) => !seenIds.has(a.action_id)),
    ];
    setActions(merged);
    setError(null);
  }, [selectedCampaignId]);

  // Load trend data for the selected campaign
  const loadTrendData = useCallback(async () => {
    if (!selectedCampaignId) return;
    setTrendLoading(true);
    try {
      const data = await fetchPerformanceTrend(selectedCampaignId);
      setTrendData(data);
    } catch {
      setTrendData([]);
    } finally {
      setTrendLoading(false);
    }
  }, [selectedCampaignId]);

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await loadCampaigns();
      setLoading(false);
    };
    init();
  }, [loadCampaigns]);

  // Load detail data when campaign changes
  useEffect(() => {
    if (selectedCampaignId) {
      loadCampaignData();
      loadTrendData();
    }
  }, [selectedCampaignId, loadCampaignData, loadTrendData]);

  // Polling with setTimeout (not setInterval)
  useEffect(() => {
    const poll = async () => {
      if (selectedCampaignId) {
        await loadCampaignData();
      }
      timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    };
    timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [selectedCampaignId, loadCampaignData]);

  const handleCampaignChange = (campaignId: string) => {
    setSelectedCampaignId(campaignId);
    setRecommendations([]);
    setActions([]);
    setTrendData([]);
  };

  const handleRecommendationUpdate = () => {
    loadCampaignData();
    loadCampaigns();
  };

  const handleTriggerTick = async () => {
    if (!selectedCampaignId || triggering) return;
    setTriggering(true);
    setTriggerResult(null);
    try {
      const result = await triggerOptimizationTick(selectedCampaignId);
      const coa = result?.coa_response ?? {};
      const results = coa.campaign_results ?? [];
      const mine =
        results.find((r) => r.campaign_id === selectedCampaignId) ??
        results[0];
      if (mine?.status === 'skipped') {
        setTriggerResult({
          kind: 'skipped',
          title: 'Campaign skipped by guardrails',
          reasons: (mine.reasons ?? []).filter(Boolean),
        });
      } else if (coa.status === 'pending') {
        setTriggerResult({
          kind: 'info',
          title: 'Tick is running in the background...',
        });
      } else {
        setTriggerResult({
          kind: 'completed',
          title: `Tick completed: ${coa.recommendations_generated ?? 0} recommendations, ${coa.actions_executed ?? 0} actions`,
        });
      }
      setTimeout(() => {
        loadCampaignData();
        loadTrendData();
      }, 2000);
    } catch (err) {
      setTriggerResult({
        kind: 'error',
        title: err instanceof Error ? err.message : 'Failed to trigger tick',
      });
    } finally {
      setTriggering(false);
    }
  };

  const handleSettingsUpdate = (updatedCampaign: CampaignRegistry) => {
    setCampaigns((prev) =>
      prev.map((c) =>
        c.campaign_id === updatedCampaign.campaign_id ? updatedCampaign : c
      )
    );
  };

  // Build synthetic ACTIVATE entries for all campaigns as baseline actions
  const syntheticActions: OptimizationAction[] = campaigns.map((c) => ({
    id: 0,
    campaign: 0,
    campaign_name: c.campaign_name,
    recommendation: null,
    action_id: `launch-${c.campaign_id}`,
    action_type: 'ACTIVATE',
    entity_type: 'campaign',
    entity_id: c.meta_campaign_id || c.campaign_id,
    old_value: {},
    new_value: {
      status: 'active',
      daily_budget_usd: c.daily_budget_usd,
      ad_sets: c.ad_sets?.length ?? 0,
      ads: c.ads?.length ?? 0,
    },
    mode: 'manual' as const,
    rationale: `Campaign "${c.campaign_name}" launched via Ad Publishing${
      c.sandbox_mode ? ' (sandbox)' : ''
    }. Daily budget $${Number(c.daily_budget_usd ?? 0).toFixed(2)}, ${c.ad_sets?.length ?? 0} ad set(s), ${c.ads?.length ?? 0} ad(s).`,
    guardrails_applied: [],
    meta_api_response: {},
    verified: true,
    verification_result: {},
    executed_at: c.start_date || c.created_at,
  })) as unknown as OptimizationAction[];

  // Merge synthetic + real actions, deduplicate by action_id
  const allActions = [...syntheticActions, ...actions];
  const seenActionIds = new Set<string>();
  const deduplicatedActions = allActions.filter((a) => {
    if (seenActionIds.has(a.action_id)) return false;
    seenActionIds.add(a.action_id);
    return true;
  });

  // Build trend data from campaign current metrics when no snapshots exist
  const effectiveTrendData =
    trendData.length > 0
      ? trendData
      : selectedCampaign &&
        (selectedCampaign.actual_cpa_usd !== null ||
          selectedCampaign.actual_roas !== null ||
          selectedCampaign.actual_ctr !== null)
      ? [
          {
            date: selectedCampaign.last_metrics_update
              ? new Date(selectedCampaign.last_metrics_update).toLocaleDateString(
                  'en-US',
                  { month: 'short', day: 'numeric' }
                )
              : 'Current',
            cpa:
              selectedCampaign.actual_cpa_usd !== null
                ? Number(selectedCampaign.actual_cpa_usd)
                : null,
            roas:
              selectedCampaign.actual_roas !== null
                ? Number(selectedCampaign.actual_roas)
                : null,
            ctr:
              selectedCampaign.actual_ctr !== null
                ? Number(selectedCampaign.actual_ctr)
                : null,
            spend:
              selectedCampaign.actual_spend_today_usd !== null
                ? Number(selectedCampaign.actual_spend_today_usd)
                : null,
          },
        ]
      : [];

  // Empty state
  if (!loading && campaigns.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <Activity className="h-12 w-12 text-brand-silver/50 mx-auto mb-4" />
        <h2 className="text-lg text-white font-medium mb-2">
          No campaigns registered
        </h2>
        <p className="text-brand-silver text-sm mb-4">
          Publish a campaign through the Ad Publishing workflow to see it here
        </p>
      </div>
    );
  }

  if (error && campaigns.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Campaign selector */}
      <CampaignSelector
        campaigns={campaigns}
        selectedId={selectedCampaignId}
        onChange={handleCampaignChange}
        loading={loading}
      />

      {/* Trigger tick button */}
      {selectedCampaign && (
        <div className="glass-card p-4 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm text-white font-medium">
                Manual Optimization
              </p>
              <p className="text-xs text-brand-silver">
                Run an optimization tick now instead of waiting for the next scheduled run.
              </p>
            </div>
            <button
              onClick={handleTriggerTick}
              disabled={triggering}
              className="btn-primary flex items-center gap-2 disabled:opacity-50"
            >
              <Zap className="h-4 w-4" />
              {triggering ? 'Triggering...' : 'Trigger Optimization Now'}
            </button>
          </div>
          {triggerResult && (
            <div
              className={`rounded-md border p-3 text-xs ${
                triggerResult.kind === 'skipped'
                  ? 'border-amber-400/30 bg-amber-400/10 text-amber-200'
                  : triggerResult.kind === 'completed'
                  ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
                  : triggerResult.kind === 'error'
                  ? 'border-red-400/30 bg-red-400/10 text-red-200'
                  : 'border-brand-electric/30 bg-brand-electric/10 text-brand-electric'
              }`}
            >
              <p className="font-medium">{triggerResult.title}</p>
              {triggerResult.reasons && triggerResult.reasons.length > 0 && (
                <ul className="mt-2 list-disc list-inside space-y-1 text-amber-100/90">
                  {triggerResult.reasons.map((r, i) => (
                    <li key={i} className="break-words">
                      {r}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Metrics cards */}
      {selectedCampaign && (
        <CampaignMetricsCard campaign={selectedCampaign} />
      )}

      {/* Performance chart */}
      {selectedCampaign && (
        <CampaignPerformanceChart
          data={effectiveTrendData}
          loading={trendLoading}
        />
      )}

      {/* Two-column layout: Recommendations + Settings */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <RecommendationsList
            campaignId={selectedCampaignId}
            recommendations={recommendations}
            onUpdate={handleRecommendationUpdate}
          />
        </div>
        <div className="lg:col-span-1">
          {selectedCampaign && (
            <OptimizationSettings
              campaign={selectedCampaign}
              onUpdate={handleSettingsUpdate}
            />
          )}
        </div>
      </div>

      {/* Recent actions — shows all campaigns */}
      <RecentActionsList actions={deduplicatedActions} />
    </div>
  );
}
