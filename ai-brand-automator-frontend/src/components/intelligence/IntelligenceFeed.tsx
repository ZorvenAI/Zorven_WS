'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, RefreshCw, Brain } from 'lucide-react';
import { useTenantRole } from '@/hooks/useTenantRole';
import {
  fetchIntelligenceReport,
  fetchIntelligenceReports,
  type CampaignIntelligenceDetail,
  type CampaignIntelligenceList,
} from '@/lib/intelligence';
import LearningCard from './LearningCard';

interface Props {
  campaignId?: string;
}

export default function IntelligenceFeed({ campaignId }: Props) {
  const { canEdit } = useTenantRole();
  const [reports, setReports] = useState<CampaignIntelligenceList[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, CampaignIntelligenceDetail>>({});
  const [detailLoading, setDetailLoading] = useState<string | null>(null);

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

      {!loading && reports.length === 0 && !error && (
        <div className="glass-card p-6 rounded-lg text-sm text-brand-silver text-center">
          No intelligence reports yet. Run a campaign optimization to generate learnings.
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
