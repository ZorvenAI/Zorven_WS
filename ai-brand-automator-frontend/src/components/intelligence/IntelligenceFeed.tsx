'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, RefreshCw, Brain, Zap } from 'lucide-react';
import { useTenantRole } from '@/hooks/useTenantRole';
import {
  fetchIntelligenceReport,
  fetchIntelligenceReports,
  triggerExtraction,
  type CampaignIntelligenceDetail,
  type CampaignIntelligenceList,
} from '@/lib/intelligence';
import { fetchCampaigns } from '@/lib/optimization';
import type { CampaignRegistry } from '@/types/optimization';
import LearningCard from './LearningCard';

interface Props {
  campaignId?: string;
  onExtractionComplete?: () => void;
}

export default function IntelligenceFeed({ campaignId, onExtractionComplete }: Props) {
  const { canEdit } = useTenantRole();
  const [reports, setReports] = useState<CampaignIntelligenceList[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, CampaignIntelligenceDetail>>({});
  const [detailLoading, setDetailLoading] = useState<string | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignRegistry[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState('');
  const [triggering, setTriggering] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);
  const [triggerMode, setTriggerMode] = useState<'store_only' | 'auto_trigger'>('store_only');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchIntelligenceReports(campaignId);
      setReports(data);
    } catch (e) {
      setReports([]);
      setError(e instanceof Error ? e.message : 'Failed to load intelligence reports');
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    fetchCampaigns()
      .then((c) => {
        setCampaigns(c);
        if (c.length === 1) setSelectedCampaign(c[0].campaign_id ?? '');
      })
      .catch(() => setCampaigns([]));
  }, []);

  async function handleTrigger() {
    if (!selectedCampaign) return;
    setTriggering(true);
    setTriggerMsg(null);
    setError(null);
    try {
      await triggerExtraction(selectedCampaign, triggerMode);
      setTriggerMsg(
        triggerMode === 'auto_trigger'
          ? 'Extraction triggered with auto-trigger — WF2 approvals may appear shortly.'
          : 'Extraction triggered — results will appear shortly.'
      );
      setTimeout(() => {
        load();
        if (triggerMode === 'auto_trigger' && onExtractionComplete) {
          onExtractionComplete();
        }
      }, 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to trigger extraction');
    } finally {
      setTriggering(false);
    }
  }

  async function toggle(id: string) {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!details[id]) {
      setDetailLoading(id);
      try {
        const detail = await fetchIntelligenceReport(id);
        setDetails((prev) => ({ ...prev, [id]: detail }));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load detail');
      } finally {
        setDetailLoading(null);
      }
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-heading font-semibold text-white flex items-center gap-2">
          <Brain className="h-5 w-5 text-brand-electric" />
          Intelligence Feed
        </h2>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="text-xs text-brand-silver hover:text-white inline-flex items-center gap-1.5 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          Refresh
        </button>
      </div>

      {error && (
        <div className="glass-card p-3 rounded-lg border border-rose-500/40 text-sm text-rose-300">
          {error}
        </div>
      )}

      {loading && reports.length === 0 && (
        <div className="glass-card p-6 rounded-lg flex items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-brand-electric" />
        </div>
      )}

      {canEdit && campaigns.length > 0 && (
        <div className="glass-card p-4 rounded-lg border border-white/5 space-y-3">
          <p className="text-xs text-brand-silver">
            Trigger intelligence extraction for a campaign
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={selectedCampaign}
              onChange={(e) => setSelectedCampaign(e.target.value)}
              className="flex-1 min-w-[180px] text-sm bg-white/5 border border-white/10 rounded-md px-3 py-1.5 text-white focus:outline-none focus:ring-1 focus:ring-brand-electric"
            >
              <option value="">Select a campaign…</option>
              {campaigns.map((c) => (
                <option key={c.campaign_id} value={c.campaign_id}>
                  {c.campaign_name || c.meta_campaign_id || `Campaign ${c.campaign_id}`}
                </option>
              ))}
            </select>
            <select
              value={triggerMode}
              onChange={(e) => setTriggerMode(e.target.value as 'store_only' | 'auto_trigger')}
              className="text-sm bg-white/5 border border-white/10 rounded-md px-3 py-1.5 text-white focus:outline-none focus:ring-1 focus:ring-brand-electric"
            >
              <option value="store_only">Store only</option>
              <option value="auto_trigger">Auto-trigger</option>
            </select>
            <button
              type="button"
              onClick={handleTrigger}
              disabled={triggering || !selectedCampaign}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-brand-electric/20 text-brand-electric hover:bg-brand-electric/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {triggering ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Zap className="h-3.5 w-3.5" />
              )}
              Trigger Extraction
            </button>
          </div>
          {triggerMsg && (
            <p className="text-xs text-emerald-400">{triggerMsg}</p>
          )}
        </div>
      )}

      {!loading && reports.length === 0 && !error && (
        <div className="glass-card p-6 rounded-lg text-sm text-brand-silver text-center">
          No intelligence reports yet. Trigger an extraction above or run a campaign optimization to generate learnings.
        </div>
      )}

      {reports.map((r) => {
        const isOpen = expanded === r.intelligence_id;
        const detail = details[r.intelligence_id];
        return (
          <div
            key={r.intelligence_id}
            className="glass-card rounded-lg border border-white/5 overflow-hidden"
          >
            <button
              type="button"
              onClick={() => toggle(r.intelligence_id)}
              className="w-full p-4 flex items-center justify-between hover:bg-white/5 transition-colors text-left"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  {isOpen ? (
                    <ChevronDown className="h-4 w-4 text-brand-silver" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-brand-silver" />
                  )}
                  <span className="text-sm font-medium text-white truncate">
                    {r.campaign_name || 'Untitled campaign'}
                  </span>
                  <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/5 text-brand-silver">
                    {r.mode}
                  </span>
                </div>
                <div className="ml-6 text-xs text-brand-silver flex items-center gap-3">
                  <span>{new Date(r.created_at).toLocaleString()}</span>
                  <span>·</span>
                  <span>{r.learnings_count} learnings</span>
                  {r.high_confidence_count > 0 && (
                    <>
                      <span>·</span>
                      <span className="text-brand-electric">
                        {r.high_confidence_count} high-confidence
                      </span>
                    </>
                  )}
                  {r.auto_reruns_triggered > 0 && (
                    <>
                      <span>·</span>
                      <span className="text-emerald-400">
                        {r.auto_reruns_triggered} auto re-runs
                      </span>
                    </>
                  )}
                </div>
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-white/5 p-4 space-y-3 bg-black/20">
                {detailLoading === r.intelligence_id && !detail && (
                  <div className="flex justify-center py-4">
                    <Loader2 className="h-4 w-4 animate-spin text-brand-electric" />
                  </div>
                )}
                {detail && detail.learnings.length === 0 && (
                  <p className="text-xs text-brand-silver">No learnings in this report.</p>
                )}
                {detail?.learnings.map((l) => (
                  <LearningCard key={l.learning_id} learning={l} canEdit={canEdit} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
