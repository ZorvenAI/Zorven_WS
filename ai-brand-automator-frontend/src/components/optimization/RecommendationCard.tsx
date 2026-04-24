'use client';

import { useState } from 'react';
import {
  StopCircle,
  TrendingUp,
  RefreshCw,
  Shuffle,
  DollarSign,
  LayoutGrid,
  Clock,
  Play,
  Check,
  X,
  AlertTriangle,
} from 'lucide-react';
import type { OptimizationRecommendation } from '@/types/optimization';
import Tooltip from './Tooltip';

interface RecommendationCardProps {
  recommendation: OptimizationRecommendation;
  onApprove: (recId: string) => void;
  onReject: (recId: string, reason?: string) => void;
  approving: boolean;
  rejecting: boolean;
}

const ACTION_ICONS: Record<string, React.ReactNode> = {
  PAUSE: <StopCircle className="w-4 h-4" />,
  SCALE: <TrendingUp className="w-4 h-4" />,
  REFRESH: <RefreshCw className="w-4 h-4" />,
  REALLOCATE: <Shuffle className="w-4 h-4" />,
  ADJUST_BID: <DollarSign className="w-4 h-4" />,
  ADJUST_PLACEMENT: <LayoutGrid className="w-4 h-4" />,
  ADJUST_SCHEDULE: <Clock className="w-4 h-4" />,
  ACTIVATE: <Play className="w-4 h-4" />,
};

const PRIORITY_STYLES: Record<
  string,
  { bg: string; text: string; border: string }
> = {
  CRITICAL: {
    bg: 'bg-red-500/20',
    text: 'text-red-400',
    border: 'border-red-500/30',
  },
  HIGH: {
    bg: 'bg-orange-500/20',
    text: 'text-orange-400',
    border: 'border-orange-500/30',
  },
  MEDIUM: {
    bg: 'bg-blue-500/20',
    text: 'text-blue-400',
    border: 'border-blue-500/30',
  },
  LOW: {
    bg: 'bg-white/10',
    text: 'text-brand-silver',
    border: 'border-white/10',
  },
};

function formatTimeRemaining(expiresAt: string): string {
  const now = new Date();
  const expires = new Date(expiresAt);
  const diffMs = expires.getTime() - now.getTime();

  if (diffMs <= 0) return 'Expired';

  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

  if (hours > 24) {
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h remaining`;
  }
  if (hours > 0) return `${hours}h ${minutes}m remaining`;
  return `${minutes}m remaining`;
}

function formatValues(values: Record<string, unknown>): string[] {
  return Object.entries(values ?? {}).map(([key, val]) => {
    const label = key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
    return `${label}: ${typeof val === 'number' ? val.toFixed(2) : String(val)}`;
  });
}

export default function RecommendationCard({
  recommendation: rec,
  onApprove,
  onReject,
  approving,
  rejecting,
}: RecommendationCardProps) {
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const priorityStyle = PRIORITY_STYLES[rec.priority] ?? PRIORITY_STYLES.LOW;
  const icon = ACTION_ICONS[rec.action_type] ?? <AlertTriangle className="w-4 h-4" />;

  const currentValues = formatValues(rec.current_values);
  const proposedValues = formatValues(rec.proposed_values);

  return (
    <div
      className={`glass-card p-4 border ${priorityStyle.border} transition-all hover:border-opacity-60`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`p-1.5 rounded-lg ${priorityStyle.bg} ${priorityStyle.text}`}>
            {icon}
          </span>
          <div>
            <p className="text-sm font-medium text-white">
              {rec.action_type.replace(/_/g, ' ')}
            </p>
            <p className="text-xs text-brand-silver">
              {rec.entity_type} / {rec.entity_id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Tooltip tabIndex={0} text="Priority level set by the AI based on potential impact and urgency. Critical items need immediate attention; Low items are minor optimizations.">
            <span
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${priorityStyle.bg} ${priorityStyle.text}`}
            >
              {rec.priority}
            </span>
          </Tooltip>
          {rec.expires_at && (
            <Tooltip tabIndex={0} text="Recommendations expire after a set window. Once expired, the underlying data may no longer be relevant and the recommendation cannot be approved.">
              <span
                className={`text-xs ${
                  rec.is_expired ? 'text-red-400' : 'text-brand-silver/60'
                }`}
              >
                <Clock className="w-3 h-3 inline mr-1" />
                {formatTimeRemaining(rec.expires_at)}
              </span>
            </Tooltip>
          )}
        </div>
      </div>

      {/* Rationale */}
      <p className="text-sm text-brand-silver mb-3">{rec.rationale}</p>

      {/* Current vs Proposed */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="bg-white/5 rounded-lg p-3">
          <Tooltip tabIndex={0} text="The current values of the settings that the AI is recommending to change.">
            <p className="text-xs font-medium text-brand-silver/60 mb-1.5 uppercase tracking-wider cursor-default">
              Current
            </p>
          </Tooltip>
          {currentValues.map((v, i) => (
            <p key={i} className="text-xs text-brand-silver">
              {v}
            </p>
          ))}
        </div>
        <div className="bg-brand-electric/5 rounded-lg p-3 border border-brand-electric/10">
          <Tooltip tabIndex={0} text="The new values that the AI recommends applying. Compare these against the current values to assess the change.">
            <p className="text-xs font-medium text-brand-electric/60 mb-1.5 uppercase tracking-wider cursor-default">
              Proposed
            </p>
          </Tooltip>
          {proposedValues.map((v, i) => (
            <p key={i} className="text-xs text-brand-electric">
              {v}
            </p>
          ))}
        </div>
      </div>

      {/* Projected impact */}
      {Object.keys(rec.projected_impact).length > 0 && (
        <div className="bg-white/5 rounded-lg p-3 mb-3">
          <Tooltip tabIndex={0} text="AI-estimated impact if this recommendation is approved. These are projections based on historical data and may vary from actual results.">
            <p className="text-xs font-medium text-brand-silver/60 mb-1.5 uppercase tracking-wider cursor-default">
              Projected Impact
            </p>
          </Tooltip>
          <div className="flex flex-wrap gap-2">
            {Object.entries(rec.projected_impact ?? {}).map(([key, val]) => (
              <span
                key={key}
                className="text-xs bg-white/5 rounded px-2 py-1 text-brand-silver"
              >
                {key.replace(/_/g, ' ')}: {String(val)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Guardrails */}
      {rec.guardrails_applied.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {rec.guardrails_applied.map((g, i) => (
            <span
              key={i}
              className="text-xs bg-amber-500/10 text-amber-400 rounded px-1.5 py-0.5"
            >
              {g}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-white/5">
        {rec.status !== 'pending' ? (
          <span
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg ${
              rec.status === 'approved' || rec.status === 'executed'
                ? 'bg-emerald-500/20 text-emerald-400'
                : rec.status === 'rejected'
                ? 'bg-red-500/20 text-red-400'
                : 'bg-white/10 text-brand-silver'
            }`}
          >
            {rec.status === 'approved' || rec.status === 'executed' ? (
              <Check className="w-3.5 h-3.5" />
            ) : rec.status === 'rejected' ? (
              <X className="w-3.5 h-3.5" />
            ) : null}
            {rec.status.charAt(0).toUpperCase() + rec.status.slice(1)}
          </span>
        ) : !showRejectInput ? (
          <>
            <button
              onClick={() => onApprove(rec.recommendation_id)}
              disabled={approving || rec.is_expired}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Check className="w-3.5 h-3.5" />
              {approving ? 'Approving...' : 'Approve'}
            </button>
            <button
              onClick={() => setShowRejectInput(true)}
              disabled={rejecting || rec.is_expired}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <X className="w-3.5 h-3.5" />
              Reject
            </button>
          </>
        ) : (
          <div className="flex items-center gap-2 flex-1">
            <input
              type="text"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Rejection reason (optional)"
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white placeholder-brand-silver/40 focus:outline-none focus:border-red-500/50"
              autoFocus
            />
            <button
              onClick={() => {
                onReject(rec.recommendation_id, rejectReason || undefined);
                setShowRejectInput(false);
                setRejectReason('');
              }}
              disabled={rejecting}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-50"
            >
              {rejecting ? 'Rejecting...' : 'Confirm'}
            </button>
            <button
              onClick={() => {
                setShowRejectInput(false);
                setRejectReason('');
              }}
              className="px-2 py-1.5 text-xs text-brand-silver hover:text-white transition-colors"
            >
              Cancel
            </button>
          </div>
        )}

        {rec.is_expired && (
          <span className="ml-auto text-xs text-red-400 font-medium">
            Expired
          </span>
        )}
      </div>
    </div>
  );
}
