'use client';

import { ChevronDown, Clock, Bell } from 'lucide-react';
import type { CampaignRegistry } from '@/types/optimization';
import Tooltip from './Tooltip';

interface CampaignSelectorProps {
  campaigns: CampaignRegistry[];
  selectedId: string | null;
  onChange: (campaignId: string) => void;
  loading: boolean;
}

export default function CampaignSelector({
  campaigns,
  selectedId,
  onChange,
  loading,
}: CampaignSelectorProps) {
  const selected = campaigns.find((c) => c.campaign_id === selectedId);

  if (loading) {
    return (
      <div className="glass-card p-4">
        <div className="h-10 bg-white/5 rounded-lg animate-pulse" />
      </div>
    );
  }

  return (
    <div className="glass-card p-4">
      <div className="flex items-center gap-4">
        <div className="flex-1 relative">
          <select
            value={selectedId ?? ''}
            onChange={(e) => onChange(e.target.value)}
            className="w-full appearance-none bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white text-sm font-medium focus:outline-none focus:border-brand-electric/50 focus:ring-1 focus:ring-brand-electric/30 pr-10 cursor-pointer"
          >
            {campaigns.map((c) => (
              <option
                key={c.campaign_id}
                value={c.campaign_id}
                className="bg-brand-midnight text-white"
              >
                {c.campaign_name} - {c.objective}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-brand-silver pointer-events-none" />
        </div>

        {selected && (
          <div className="flex items-center gap-3">
            {/* Status badge */}
            <Tooltip tabIndex={0} text="Current campaign delivery status on Meta Ads. Active means ads are running, Paused means delivery is stopped, Completed means the campaign has ended.">
              <span
                className={`px-2.5 py-1 text-xs font-medium rounded-full ${
                  selected.status === 'active'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : selected.status === 'paused'
                      ? 'bg-amber-500/20 text-amber-400'
                      : selected.status === 'completed'
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'bg-white/10 text-brand-silver'
                }`}
              >
                {selected.status.charAt(0).toUpperCase() +
                  selected.status.slice(1)}
              </span>
            </Tooltip>

            {/* Age badge */}
            <Tooltip tabIndex={0} text="Number of days since the campaign started running. Younger campaigns may need more time before optimization patterns emerge.">
              <span className="flex items-center gap-1 text-xs text-brand-silver">
                <Clock className="w-3.5 h-3.5" />
                {selected.age_days}d old
              </span>
            </Tooltip>

            {/* Pending recommendations badge */}
            {selected.pending_recommendations_count > 0 && (
              <Tooltip tabIndex={0} text="AI-generated optimization recommendations waiting for your review. Approve or reject each to guide the optimization engine.">
                <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full bg-brand-electric/20 text-brand-electric">
                  <Bell className="w-3.5 h-3.5" />
                  {selected.pending_recommendations_count} pending
                </span>
              </Tooltip>
            )}

            {/* Sandbox badge */}
            {selected.sandbox_mode && (
              <Tooltip tabIndex={0} text="This campaign is in sandbox mode. All optimization actions are simulated and not applied to real Meta Ads.">
                <span className="px-2.5 py-1 text-xs font-medium rounded-full bg-amber-500/20 text-amber-400">
                  Sandbox
                </span>
              </Tooltip>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
