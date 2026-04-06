'use client';

import { useState } from 'react';
import {
  Settings,
  Shield,
  AlertTriangle,
  Calendar,
  Target,
  DollarSign,
} from 'lucide-react';
import type { CampaignRegistry } from '@/types/optimization';
import { updateCampaignSettings } from '@/lib/optimization';

interface OptimizationSettingsProps {
  campaign: CampaignRegistry;
  onUpdate: (campaign: CampaignRegistry) => void;
}

export default function OptimizationSettings({
  campaign,
  onUpdate,
}: OptimizationSettingsProps) {
  const [updating, setUpdating] = useState(false);

  const handleModeToggle = async () => {
    const newMode =
      campaign.optimization_mode === 'manual' ? 'autonomous' : 'manual';
    setUpdating(true);
    try {
      const updated = await updateCampaignSettings(campaign.campaign_id, {
        optimization_mode: newMode,
      });
      onUpdate(updated);
    } catch (err) {
      console.error('Failed to update optimization mode:', err);
    } finally {
      setUpdating(false);
    }
  };

  const guardrailEntries = Object.entries(campaign.guardrail_config ?? {});

  return (
    <div className="glass-card p-6 space-y-5">
      <div className="flex items-center gap-2">
        <Settings className="w-4 h-4 text-brand-silver" />
        <h3 className="text-sm font-medium text-white">
          Optimization Settings
        </h3>
      </div>

      {/* Sandbox Warning */}
      {campaign.sandbox_mode && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-medium text-amber-400">Sandbox Mode</p>
            <p className="text-xs text-amber-400/70 mt-0.5">
              Actions are simulated and not applied to Meta Ads.
            </p>
          </div>
        </div>
      )}

      {/* Mode Toggle */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
          Optimization Mode
        </p>
        <div className="flex items-center gap-3">
          <button
            onClick={handleModeToggle}
            disabled={updating}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand-electric/30 disabled:opacity-50 ${
              campaign.optimization_mode === 'autonomous'
                ? 'bg-brand-electric'
                : 'bg-white/20'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 rounded-full bg-white transform transition-transform ${
                campaign.optimization_mode === 'autonomous'
                  ? 'translate-x-6'
                  : 'translate-x-1'
              }`}
            />
          </button>
          <span className="text-sm text-white">
            {campaign.optimization_mode === 'autonomous'
              ? 'Autonomous'
              : 'Manual'}
          </span>
        </div>
        <p className="text-xs text-brand-silver/60">
          {campaign.optimization_mode === 'autonomous'
            ? 'Recommendations are auto-applied within guardrails'
            : 'All recommendations require manual approval'}
        </p>
      </div>

      {/* Campaign Info */}
      <div className="space-y-3 pt-2 border-t border-white/5">
        <p className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
          Campaign Info
        </p>

        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs">
            <Calendar className="w-3.5 h-3.5 text-brand-silver/40" />
            <span className="text-brand-silver">
              Started:{' '}
              {new Date(campaign.start_date).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}
            </span>
          </div>
          {campaign.end_date && (
            <div className="flex items-center gap-2 text-xs">
              <Calendar className="w-3.5 h-3.5 text-brand-silver/40" />
              <span className="text-brand-silver">
                Ends:{' '}
                {new Date(campaign.end_date).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </span>
            </div>
          )}
          <div className="flex items-center gap-2 text-xs">
            <DollarSign className="w-3.5 h-3.5 text-brand-silver/40" />
            <span className="text-brand-silver">
              Daily: ${Number(campaign.daily_budget_usd ?? 0).toFixed(2)}
            </span>
          </div>
          {campaign.target_cpa_usd != null && (
            <div className="flex items-center gap-2 text-xs">
              <Target className="w-3.5 h-3.5 text-brand-silver/40" />
              <span className="text-brand-silver">
                Target CPA: ${Number(campaign.target_cpa_usd).toFixed(2)}
              </span>
            </div>
          )}
          {campaign.target_roas != null && (
            <div className="flex items-center gap-2 text-xs">
              <Target className="w-3.5 h-3.5 text-brand-silver/40" />
              <span className="text-brand-silver">
                Target ROAS: {Number(campaign.target_roas).toFixed(1)}x
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Guardrails */}
      {guardrailEntries.length > 0 && (
        <div className="space-y-3 pt-2 border-t border-white/5">
          <div className="flex items-center gap-2">
            <Shield className="w-3.5 h-3.5 text-brand-silver/60" />
            <p className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
              Guardrail Config
            </p>
          </div>
          <div className="space-y-1.5">
            {guardrailEntries.map(([key, value]) => (
              <div
                key={key}
                className="flex items-center justify-between text-xs bg-white/5 rounded-lg px-3 py-2"
              >
                <span className="text-brand-silver">
                  {key.replace(/_/g, ' ')}
                </span>
                <span className="text-white font-medium">
                  {String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Ad Sets & Ads count */}
      <div className="pt-2 border-t border-white/5">
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white/5 rounded-lg p-3 text-center">
            <p className="text-lg font-heading font-bold text-white">
              {campaign.ad_sets.length}
            </p>
            <p className="text-xs text-brand-silver/60">Ad Sets</p>
          </div>
          <div className="bg-white/5 rounded-lg p-3 text-center">
            <p className="text-lg font-heading font-bold text-white">
              {campaign.ads.length}
            </p>
            <p className="text-xs text-brand-silver/60">Ads</p>
          </div>
        </div>
      </div>
    </div>
  );
}
