'use client';

import { useState, useEffect } from 'react';
import { FileText, Zap, GitBranch, MessageSquare } from 'lucide-react';
import { apiClient } from '@/lib/api';

interface CardConfig {
  title: string;
  icon: React.ReactNode;
  endpoint: string;
  formatChange: (count: number) => string;
}

const CARD_CONFIGS: CardConfig[] = [
  {
    title: 'Total Assets',
    icon: <FileText className="h-5 w-5 text-brand-electric" />,
    endpoint: '/assets/',
    formatChange: (n) => `${n} files uploaded`,
  },
  {
    title: 'AI Interactions',
    icon: <Zap className="h-5 w-5 text-brand-mint" />,
    endpoint: '/ai/generations/',
    formatChange: (n) => `${n} generations`,
  },
  {
    title: 'Workflows Run',
    icon: <GitBranch className="h-5 w-5 text-purple-400" />,
    endpoint: '/orchestration/jobs/?status=completed',
    formatChange: (n) => `${n} completed`,
  },
  {
    title: 'Chat Sessions',
    icon: <MessageSquare className="h-5 w-5 text-amber-400" />,
    endpoint: '/ai/chat-sessions/',
    formatChange: (n) => `${n} sessions`,
  },
];

/** Extract count from a DRF paginated response or plain array. */
function extractCount(data: unknown): number {
  if (Array.isArray(data)) return data.length;
  if (data && typeof data === 'object' && 'count' in data) {
    return (data as { count: number }).count;
  }
  return 0;
}

interface CardState {
  value: string;
  change: string;
  changeType: 'positive' | 'neutral' | 'negative';
}

export function OverviewCards() {
  const [cardStates, setCardStates] = useState<CardState[]>(
    CARD_CONFIGS.map(() => ({
      value: '0',
      change: 'Loading...',
      changeType: 'neutral' as const,
    }))
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const responses = await Promise.all(
          CARD_CONFIGS.map((cfg) => apiClient.get(cfg.endpoint))
        );
        const dataList = await Promise.all(responses.map((r) => r.json()));
        const counts = dataList.map(extractCount);

        setCardStates(
          counts.map((count, i) => ({
            value: count.toLocaleString(),
            change: CARD_CONFIGS[i].formatChange(count),
            changeType: count > 0 ? ('positive' as const) : ('neutral' as const),
          }))
        );
        setLoading(false);
      } catch (error) {
        console.error('Error fetching dashboard data:', error);
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {CARD_CONFIGS.map((cfg) => (
          <div key={cfg.title} className="dashboard-card animate-pulse">
            <div className="h-4 bg-white/10 rounded w-1/2 mb-4"></div>
            <div className="h-8 bg-white/10 rounded w-3/4"></div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {CARD_CONFIGS.map((cfg, index) => {
        const state = cardStates[index];
        return (
          <div key={cfg.title} className="dashboard-card">
            <div className="flex items-center justify-between">
              <h3 className="font-heading text-sm font-medium text-brand-silver/70">{cfg.title}</h3>
              {cfg.icon}
            </div>
            <div className="mt-2 flex items-baseline">
              <p className="text-2xl font-heading font-semibold text-white">{state.value}</p>
              <p
                className={`ml-2 text-sm ${
                  state.changeType === 'positive'
                    ? 'text-brand-mint'
                    : 'text-brand-silver/70'
                }`}
              >
                {state.change}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
