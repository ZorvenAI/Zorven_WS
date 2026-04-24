'use client';

import { useState } from 'react';
import { CheckCheck, Inbox } from 'lucide-react';
import type { OptimizationRecommendation } from '@/types/optimization';
import {
  approveRecommendation,
  rejectRecommendation,
  batchApproveRecommendations,
} from '@/lib/optimization';
import RecommendationCard from './RecommendationCard';
import Tooltip from './Tooltip';

interface RecommendationsListProps {
  campaignId: string | null;
  recommendations: OptimizationRecommendation[];
  onUpdate: () => void;
}

export default function RecommendationsList({
  campaignId,
  recommendations,
  onUpdate,
}: RecommendationsListProps) {
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [batchApproving, setBatchApproving] = useState(false);

  const handleApprove = async (recId: string) => {
    if (!campaignId) return;
    setApprovingId(recId);
    try {
      await approveRecommendation(campaignId, recId);
      onUpdate();
    } catch (err) {
      console.error('Failed to approve recommendation:', err);
    } finally {
      setApprovingId(null);
    }
  };

  const handleReject = async (recId: string, reason?: string) => {
    if (!campaignId) return;
    setRejectingId(recId);
    try {
      await rejectRecommendation(campaignId, recId, reason);
      onUpdate();
    } catch (err) {
      console.error('Failed to reject recommendation:', err);
    } finally {
      setRejectingId(null);
    }
  };

  const handleBatchApprove = async () => {
    if (!campaignId) return;
    setBatchApproving(true);
    try {
      const result = await batchApproveRecommendations(campaignId);
      console.info(
        `Batch approved: ${result.approved_count}, expired: ${result.expired_count}`
      );
      onUpdate();
    } catch (err) {
      console.error('Failed to batch approve:', err);
    } finally {
      setBatchApproving(false);
    }
  };

  // Sort by priority: CRITICAL > HIGH > MEDIUM > LOW
  const priorityOrder: Record<string, number> = {
    CRITICAL: 0,
    HIGH: 1,
    MEDIUM: 2,
    LOW: 3,
  };
  const sorted = [...recommendations].sort(
    (a, b) =>
      (priorityOrder[a.priority] ?? 99) - (priorityOrder[b.priority] ?? 99)
  );

  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <Tooltip tabIndex={0} text="AI-generated suggestions to improve campaign performance. Each recommendation includes a proposed change, its rationale, and projected impact. Review and approve or reject each one.">
            <h3 className="text-sm font-medium text-white cursor-default">
              Recommendations
            </h3>
          </Tooltip>
          <p className="text-xs text-brand-silver/60 mt-0.5">
            {recommendations.length} recommendation
            {recommendations.length !== 1 ? 's' : ''}
            {recommendations.filter((r) => r.status === 'pending').length > 0 &&
              ` (${recommendations.filter((r) => r.status === 'pending').length} pending)`}
          </p>
        </div>
        {recommendations.length > 1 && (
          <Tooltip text="Approve all pending recommendations at once. Expired recommendations will be skipped automatically.">
            <button
              onClick={handleBatchApprove}
              disabled={batchApproving}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-brand-electric/20 text-brand-electric hover:bg-brand-electric/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <CheckCheck className="w-3.5 h-3.5" />
              {batchApproving ? 'Approving All...' : 'Approve All'}
            </button>
          </Tooltip>
        )}
      </div>

      {sorted.length === 0 ? (
        <div className="text-center py-8">
          <Inbox className="h-8 w-8 text-brand-silver/30 mx-auto mb-2" />
          <p className="text-sm text-brand-silver/60">
            No pending recommendations
          </p>
          <p className="text-xs text-brand-silver/40 mt-1">
            Recommendations will appear after the next optimization tick
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {sorted.map((rec) => (
            <RecommendationCard
              key={rec.recommendation_id}
              recommendation={rec}
              onApprove={handleApprove}
              onReject={handleReject}
              approving={approvingId === rec.recommendation_id}
              rejecting={rejectingId === rec.recommendation_id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
