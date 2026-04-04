/**
 * ApprovalPanel — renders ad-publishing preview data with approve/reject controls.
 *
 * Shown when a job is in `awaiting_approval` status. Displays campaign overview,
 * ad set breakdown, creative previews, and action buttons.
 */

'use client';

import { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Eye,
  DollarSign,
  Users,
  Image,
  Shield,
  Loader2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { approveJob } from '@/lib/orchestration';

interface AdSetPreview {
  ad_set_name?: string;
  name?: string;
  persona?: string;
  funnel_stage?: string;
  daily_budget_usd?: number;
  daily_budget_cents?: number;
  targeting_summary?: string;
  creative_count?: number;
  creatives?: Array<{
    headline?: string;
    body?: string;
    primary_text?: string;
    cta_type?: string;
    image_url?: string;
    image_hash?: string;
    preview_html?: string;
  }>;
}

interface PreviewData {
  campaign_name?: string;
  objective?: string;
  total_daily_budget_usd?: number;
  duration_days?: number;
  ad_sets?: AdSetPreview[];
  previews?: Record<string, string>;
  sandbox_mode?: boolean;
  special_ad_category?: string;
}

interface ApprovalPanelProps {
  jobId: string;
  approvalRequestId: string;
  previewData: PreviewData;
  sandboxMode: boolean;
  planWarnings?: string[];
  onApprovalComplete?: () => void;
}

export default function ApprovalPanel({
  jobId,
  approvalRequestId,
  previewData,
  sandboxMode,
  planWarnings,
  onApprovalComplete,
}: ApprovalPanelProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedAdSets, setExpandedAdSets] = useState<Set<number>>(new Set([0]));
  const [feedback, setFeedback] = useState('');
  const [productionConfirmed, setProductionConfirmed] = useState(false);

  const adSets = previewData.ad_sets ?? [];
  const totalBudget = previewData.total_daily_budget_usd ?? 0;
  const totalCreatives = adSets.reduce(
    (sum, s) => sum + (s.creative_count ?? s.creatives?.length ?? 0),
    0,
  );

  const toggleAdSet = (idx: number) => {
    setExpandedAdSets((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const handleDecision = async (decision: 'approve_all' | 'reject') => {
    setIsSubmitting(true);
    setError(null);
    try {
      const res = await approveJob(jobId, {
        approval_request_id: approvalRequestId,
        decision,
        feedback: feedback || undefined,
        production_confirmed: decision === 'approve_all' ? productionConfirmed : undefined,
      });
      setResult(res);
      onApprovalComplete?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit decision');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Already submitted
  if (result) {
    const isApproved = result.status === 'published' || result.status === 'approved';
    return (
      <div className="space-y-4">
        <div className={`flex items-center gap-3 p-4 rounded-xl border ${
          isApproved
            ? 'border-emerald-500/30 bg-emerald-500/10'
            : 'border-red-500/30 bg-red-500/10'
        }`}>
          {isApproved ? (
            <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
          ) : (
            <XCircle className="w-6 h-6 text-red-400 shrink-0" />
          )}
          <div>
            <p className={`text-sm font-medium ${isApproved ? 'text-emerald-300' : 'text-red-300'}`}>
              {isApproved ? 'Campaign Approved & Published' : 'Campaign Rejected'}
            </p>
            <p className="text-xs text-brand-silver/50 mt-0.5">
              {isApproved
                ? 'Ads are now live on Meta. Monitor performance in Meta Ads Manager.'
                : 'The campaign was rejected. No ads will be published.'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Mode badge */}
      <div className="flex items-center gap-2">
        <Shield className="w-4 h-4 text-amber-400" />
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
          sandboxMode
            ? 'bg-amber-500/20 text-amber-300'
            : 'bg-red-500/20 text-red-300'
        }`}>
          {sandboxMode ? 'Sandbox Mode' : 'Production Mode'}
        </span>
        {sandboxMode && (
          <span className="text-[10px] text-brand-silver/40">
            No real ads will be published
          </span>
        )}
      </div>

      {/* Campaign overview */}
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-3">
        <h4 className="text-sm font-semibold text-white">
          {previewData.campaign_name ?? 'Campaign'}
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat
            icon={<Eye className="w-3.5 h-3.5" />}
            label="Objective"
            value={previewData.objective ?? 'N/A'}
          />
          <Stat
            icon={<DollarSign className="w-3.5 h-3.5" />}
            label="Daily Budget"
            value={`$${totalBudget.toFixed(2)}`}
          />
          <Stat
            icon={<Users className="w-3.5 h-3.5" />}
            label="Ad Sets"
            value={String(adSets.length)}
          />
          <Stat
            icon={<Image className="w-3.5 h-3.5" />}
            label="Creatives"
            value={String(totalCreatives)}
          />
        </div>
        {previewData.duration_days && (
          <p className="text-[11px] text-brand-silver/40">
            Duration: {previewData.duration_days} days
            {previewData.special_ad_category && (
              <> &middot; Special Ad Category: {previewData.special_ad_category}</>
            )}
          </p>
        )}
      </div>

      {/* Warnings */}
      {planWarnings && planWarnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-1">
          <div className="flex items-center gap-1.5 text-amber-300 text-xs font-medium">
            <AlertTriangle className="w-3.5 h-3.5" />
            Warnings
          </div>
          {planWarnings.map((w, i) => (
            <p key={i} className="text-[11px] text-amber-200/70 pl-5">{w}</p>
          ))}
        </div>
      )}

      {/* Ad Sets */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">
          Ad Sets
        </h4>
        {adSets.map((adSet, idx) => {
          const name = adSet.ad_set_name ?? adSet.name ?? `Ad Set ${idx + 1}`;
          const isOpen = expandedAdSets.has(idx);
          const budget = adSet.daily_budget_usd ?? (adSet.daily_budget_cents ? adSet.daily_budget_cents / 100 : 0);
          const creatives = adSet.creatives ?? [];

          return (
            <div
              key={idx}
              className="rounded-lg border border-white/10 bg-white/[0.02] overflow-hidden"
            >
              <button
                onClick={() => toggleAdSet(idx)}
                className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-white/[0.03] transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-brand-silver">{name}</span>
                  {adSet.funnel_stage && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-brand-electric/15 text-brand-electric/80">
                      {adSet.funnel_stage}
                    </span>
                  )}
                  {adSet.persona && (
                    <span className="text-[10px] text-brand-silver/40 truncate max-w-[150px]">
                      {adSet.persona}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-brand-silver/40">
                    ${budget.toFixed(2)}/day &middot; {creatives.length} creatives
                  </span>
                  {isOpen ? (
                    <ChevronUp className="w-4 h-4 text-brand-silver/30" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-brand-silver/30" />
                  )}
                </div>
              </button>

              {isOpen && (
                <div className="px-4 pb-4 space-y-3 border-t border-white/5">
                  {adSet.targeting_summary && (
                    <p className="text-[11px] text-brand-silver/50 pt-3">
                      <span className="text-brand-silver/30">Targeting:</span> {adSet.targeting_summary}
                    </p>
                  )}
                  {creatives.length > 0 && (
                    <div className="grid grid-cols-1 gap-2">
                      {creatives.map((creative, cIdx) => (
                        <div
                          key={cIdx}
                          className="flex gap-3 p-3 rounded-lg bg-white/[0.03] border border-white/5"
                        >
                          {creative.image_url && (
                            <div className="w-16 h-16 rounded-md overflow-hidden shrink-0 bg-white/5">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={creative.image_url}
                                alt={creative.headline ?? 'Ad creative'}
                                className="w-full h-full object-cover"
                              />
                            </div>
                          )}
                          <div className="flex-1 min-w-0 space-y-1">
                            {creative.headline && (
                              <p className="text-xs font-medium text-white truncate">
                                {creative.headline}
                              </p>
                            )}
                            {(creative.body ?? creative.primary_text) && (
                              <p className="text-[11px] text-brand-silver/60 line-clamp-2">
                                {creative.body ?? creative.primary_text}
                              </p>
                            )}
                            {creative.cta_type && (
                              <span className="inline-block text-[10px] px-1.5 py-0.5 rounded bg-brand-electric/10 text-brand-electric/70">
                                {creative.cta_type.replace(/_/g, ' ')}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {creatives.length === 0 && (
                    <p className="text-[11px] text-brand-silver/30 pt-2">
                      {adSet.creative_count ?? 0} creatives prepared
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Feedback */}
      <div>
        <label className="text-xs text-brand-silver/50 block mb-1">
          Feedback (optional)
        </label>
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="Add notes for the team..."
          className="w-full bg-white/[0.03] border border-white/10 rounded-lg px-3 py-2 text-sm text-brand-silver placeholder:text-brand-silver/20 focus:outline-none focus:border-brand-electric/40 resize-none"
          rows={2}
        />
      </div>

      {/* Production confirmation */}
      {!sandboxMode && (
        <label className="flex items-start gap-2 p-3 rounded-lg border border-red-500/20 bg-red-500/5 cursor-pointer">
          <input
            type="checkbox"
            checked={productionConfirmed}
            onChange={(e) => setProductionConfirmed(e.target.checked)}
            className="mt-0.5 accent-red-500"
          />
          <div>
            <p className="text-xs font-medium text-red-300">
              I confirm this campaign should go live
            </p>
            <p className="text-[10px] text-red-300/60 mt-0.5">
              Real ads will be published and billed to the connected Meta account.
            </p>
          </div>
        </label>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-300">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={() => handleDecision('approve_all')}
          disabled={isSubmitting || (!sandboxMode && !productionConfirmed)}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-600/30 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
        >
          {isSubmitting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <CheckCircle2 className="w-4 h-4" />
          )}
          {sandboxMode ? 'Approve (Sandbox)' : 'Approve & Publish'}
        </button>
        <button
          onClick={() => handleDecision('reject')}
          disabled={isSubmitting}
          className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-red-500/30 hover:bg-red-500/10 disabled:opacity-30 text-red-400 text-sm font-medium transition-colors"
        >
          <XCircle className="w-4 h-4" />
          Reject
        </button>
      </div>
    </div>
  );
}

/* ── Stat chip ── */

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 p-2 rounded-lg bg-white/[0.03]">
      <div className="text-brand-electric/60">{icon}</div>
      <div>
        <p className="text-[10px] text-brand-silver/40">{label}</p>
        <p className="text-xs text-brand-silver font-medium truncate">{value}</p>
      </div>
    </div>
  );
}
