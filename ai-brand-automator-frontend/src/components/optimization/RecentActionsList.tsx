'use client';

import { CheckCircle2, XCircle, History } from 'lucide-react';
import type { OptimizationAction } from '@/types/optimization';
import Tooltip from './Tooltip';

interface RecentActionsListProps {
  actions: OptimizationAction[];
}

const ACTION_COLORS: Record<string, string> = {
  PAUSE: 'text-amber-400',
  SCALE: 'text-emerald-400',
  REALLOCATE: 'text-blue-400',
  REFRESH: 'text-purple-400',
  ADJUST_BID: 'text-cyan-400',
  ADJUST_PLACEMENT: 'text-pink-400',
  ADJUST_SCHEDULE: 'text-orange-400',
  ACTIVATE: 'text-emerald-400',
};

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function RecentActionsList({
  actions,
}: RecentActionsListProps) {
  // Show last 20 actions, sorted by most recent first
  const recent = [...actions]
    .sort(
      (a, b) =>
        new Date(b.executed_at).getTime() - new Date(a.executed_at).getTime()
    )
    .slice(0, 20);

  return (
    <div className="glass-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <History className="w-4 h-4 text-brand-silver" />
        <Tooltip text="Log of optimization actions executed on this campaign. Includes both autonomous (auto-applied) and manual (human-approved) actions. Shows the most recent 20 actions.">
          <h3 className="text-sm font-medium text-white cursor-default">Recent Actions</h3>
        </Tooltip>
        <span className="text-xs text-brand-silver/60">
          ({recent.length} shown)
        </span>
      </div>

      {recent.length === 0 ? (
        <div className="text-center py-8">
          <History className="h-8 w-8 text-brand-silver/30 mx-auto mb-2" />
          <p className="text-sm text-brand-silver/60">
            No actions executed yet
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-brand-silver/60 border-b border-white/5">
                <th className="text-left py-2 font-medium">
                  <Tooltip text="When the action was executed.">
                    <span className="cursor-default">Date</span>
                  </Tooltip>
                </th>
                <th className="text-left py-2 font-medium">
                  <Tooltip text="The campaign this action was applied to.">
                    <span className="cursor-default">Campaign</span>
                  </Tooltip>
                </th>
                <th className="text-left py-2 font-medium">
                  <Tooltip text="The type of optimization action taken (e.g., Pause, Scale, Reallocate, Adjust Bid).">
                    <span className="cursor-default">Action</span>
                  </Tooltip>
                </th>
                <th className="text-left py-2 font-medium">
                  <Tooltip text="The specific entity (campaign, ad set, or ad) the action was applied to.">
                    <span className="cursor-default">Entity</span>
                  </Tooltip>
                </th>
                <th className="text-left py-2 font-medium">
                  <Tooltip text="How the action was applied. Autonomous means auto-applied by the AI; Manual means a human approved it first.">
                    <span className="cursor-default">Mode</span>
                  </Tooltip>
                </th>
                <th className="text-center py-2 font-medium">
                  <Tooltip text="Whether the action was verified as successfully applied on Meta Ads after execution.">
                    <span className="cursor-default">Verified</span>
                  </Tooltip>
                </th>
                <th className="text-left py-2 font-medium">
                  <Tooltip text="The AI-generated explanation for why this action was recommended and executed.">
                    <span className="cursor-default">Rationale</span>
                  </Tooltip>
                </th>
              </tr>
            </thead>
            <tbody>
              {recent.map((action) => (
                <tr
                  key={action.action_id}
                  className="border-b border-white/5 hover:bg-white/5 transition-colors"
                >
                  <td className="py-2.5 text-brand-silver whitespace-nowrap">
                    {formatDate(action.executed_at)}
                  </td>
                  <td className="py-2.5 text-brand-silver text-xs max-w-[140px] truncate">
                    {(action as unknown as { campaign_name?: string }).campaign_name ?? '—'}
                  </td>
                  <td className="py-2.5">
                    <span
                      className={`font-medium ${
                        ACTION_COLORS[action.action_type] ?? 'text-white'
                      }`}
                    >
                      {action.action_type.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="py-2.5 text-brand-silver">
                    <span className="text-xs bg-white/5 rounded px-1.5 py-0.5">
                      {action.entity_type}
                    </span>{' '}
                    <span className="text-xs text-brand-silver/60">
                      {action.entity_id}
                    </span>
                  </td>
                  <td className="py-2.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        action.mode === 'autonomous'
                          ? 'bg-brand-electric/20 text-brand-electric'
                          : 'bg-white/10 text-brand-silver'
                      }`}
                    >
                      {action.mode}
                    </span>
                  </td>
                  <td className="py-2.5 text-center">
                    {action.verified ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 mx-auto" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-400/60 mx-auto" />
                    )}
                  </td>
                  <td className="py-2.5 text-brand-silver/60 text-xs max-w-xs truncate">
                    {action.rationale}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
