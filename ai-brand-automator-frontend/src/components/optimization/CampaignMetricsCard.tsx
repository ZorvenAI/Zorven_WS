'use client';

import {
  DollarSign,
  TrendingUp,
  MousePointerClick,
  Wallet,
} from 'lucide-react';
import type { CampaignRegistry } from '@/types/optimization';

interface CampaignMetricsCardProps {
  campaign: CampaignRegistry;
}

interface MetricCardData {
  label: string;
  value: string;
  target: string | null;
  icon: React.ReactNode;
  status: 'good' | 'warning' | 'neutral';
  progress: number | null;
}

export default function CampaignMetricsCard({
  campaign,
}: CampaignMetricsCardProps) {
  const iconCls = 'w-5 h-5';

  // Django serializes DecimalField as strings — coerce defensively.
  const toNum = (v: unknown): number | null => {
    if (v === null || v === undefined || v === '') return null;
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : null;
  };

  const targetCpa = toNum(campaign.target_cpa_usd);
  const targetRoas = toNum(campaign.target_roas);
  const actualCpa = toNum(campaign.actual_cpa_usd);
  const actualRoas = toNum(campaign.actual_roas);
  const actualCtr = toNum(campaign.actual_ctr);
  const spendToday = toNum(campaign.actual_spend_today_usd);
  const daily = toNum(campaign.daily_budget_usd) ?? 0;
  const lifetime = toNum(campaign.lifetime_budget_usd);
  const ageDays = toNum(campaign.age_days) ?? 0;

  // CPA is good when actual ≤ target; ROAS is good when actual ≥ target.
  const cpaStatus: MetricCardData['status'] =
    actualCpa !== null && targetCpa !== null
      ? actualCpa <= targetCpa
        ? 'good'
        : 'warning'
      : 'neutral';
  const roasStatus: MetricCardData['status'] =
    actualRoas !== null && targetRoas !== null
      ? actualRoas >= targetRoas
        ? 'good'
        : 'warning'
      : 'neutral';

  const metrics: MetricCardData[] = [
    {
      label: 'CPA',
      value: actualCpa !== null ? `$${actualCpa.toFixed(2)}` : '--',
      target: targetCpa !== null ? `Target: $${targetCpa.toFixed(2)}` : null,
      icon: <DollarSign className={iconCls} />,
      status: cpaStatus,
      progress: null,
    },
    {
      label: 'ROAS',
      value: actualRoas !== null ? `${actualRoas.toFixed(1)}x` : '--',
      target: targetRoas !== null ? `Target: ${targetRoas.toFixed(1)}x` : null,
      icon: <TrendingUp className={iconCls} />,
      status: roasStatus,
      progress: null,
    },
    {
      label: 'CTR',
      value: actualCtr !== null ? `${actualCtr.toFixed(2)}%` : '--',
      target: null,
      icon: <MousePointerClick className={iconCls} />,
      status: 'neutral',
      progress: null,
    },
    {
      label: 'Daily Spend',
      value:
        spendToday !== null
          ? `$${spendToday.toFixed(2)}`
          : `$${daily.toFixed(2)}`,
      target:
        spendToday !== null
          ? `Budget: $${daily.toFixed(2)}`
          : lifetime !== null
            ? `Lifetime: $${lifetime.toFixed(0)}`
            : `Daily budget`,
      icon: <Wallet className={iconCls} />,
      status: 'neutral',
      progress:
        lifetime && lifetime > 0
          ? Math.min((daily * ageDays) / lifetime, 1) * 100
          : null,
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((metric) => (
        <div key={metric.label} className="glass-card p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-brand-silver uppercase tracking-wider">
              {metric.label}
            </span>
            <span
              className={`p-1.5 rounded-lg ${
                metric.status === 'good'
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : metric.status === 'warning'
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-white/10 text-brand-silver'
              }`}
            >
              {metric.icon}
            </span>
          </div>

          <p className="text-2xl font-heading font-bold text-white">
            {metric.value}
          </p>

          {metric.target && (
            <p className="text-xs text-brand-silver mt-1">{metric.target}</p>
          )}

          {metric.progress !== null && (
            <div className="mt-2">
              <div className="w-full bg-white/10 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full transition-all ${
                    metric.progress > 80
                      ? 'bg-red-400'
                      : metric.progress > 50
                        ? 'bg-amber-400'
                        : 'bg-brand-electric'
                  }`}
                  style={{ width: `${Math.min(metric.progress, 100)}%` }}
                />
              </div>
              <p className="text-xs text-brand-silver/60 mt-1">
                {metric.progress.toFixed(0)}% of lifetime budget
              </p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
