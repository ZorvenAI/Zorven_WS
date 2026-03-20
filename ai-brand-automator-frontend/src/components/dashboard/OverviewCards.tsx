'use client';

import { useState, useEffect } from 'react';
import { FileText, Zap, GitBranch, MessageSquare } from 'lucide-react';
import { apiClient } from '@/lib/api';

interface CardData {
  title: string;
  value: string;
  change: string;
  changeType: 'positive' | 'neutral' | 'negative';
  icon: React.ReactNode;
}

/** Extract count from a DRF paginated response or plain array. */
function extractCount(data: unknown): number {
  if (Array.isArray(data)) return data.length;
  if (data && typeof data === 'object' && 'count' in data) {
    return (data as { count: number }).count;
  }
  return 0;
}

export function OverviewCards() {
  const [cards, setCards] = useState<CardData[]>([
    {
      title: 'Total Assets',
      value: '0',
      change: 'Loading...',
      changeType: 'neutral' as const,
      icon: <FileText className="h-5 w-5 text-brand-electric" />,
    },
    {
      title: 'AI Interactions',
      value: '0',
      change: 'Loading...',
      changeType: 'neutral' as const,
      icon: <Zap className="h-5 w-5 text-brand-mint" />,
    },
    {
      title: 'Workflows Run',
      value: '0',
      change: 'Loading...',
      changeType: 'neutral' as const,
      icon: <GitBranch className="h-5 w-5 text-purple-400" />,
    },
    {
      title: 'Chat Sessions',
      value: '0',
      change: 'Loading...',
      changeType: 'neutral' as const,
      icon: <MessageSquare className="h-5 w-5 text-amber-400" />,
    },
  ]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const [assetsRes, aiRes, jobsRes, chatRes] = await Promise.all([
          apiClient.get('/assets/'),
          apiClient.get('/ai/generations/'),
          apiClient.get('/orchestration/jobs/?status=completed'),
          apiClient.get('/ai/chat-sessions/'),
        ]);

        const [assetsData, aiData, jobsData, chatData] = await Promise.all([
          assetsRes.json(),
          aiRes.json(),
          jobsRes.json(),
          chatRes.json(),
        ]);

        const assetsCount = extractCount(assetsData);
        const aiCount = extractCount(aiData);
        const jobsCount = extractCount(jobsData);
        const chatCount = extractCount(chatData);

        setCards([
          {
            title: 'Total Assets',
            value: assetsCount.toLocaleString(),
            change: `${assetsCount} files uploaded`,
            changeType: assetsCount > 0 ? 'positive' : 'neutral',
            icon: <FileText className="h-5 w-5 text-brand-electric" />,
          },
          {
            title: 'AI Interactions',
            value: aiCount.toLocaleString(),
            change: `${aiCount} generations`,
            changeType: aiCount > 0 ? 'positive' : 'neutral',
            icon: <Zap className="h-5 w-5 text-brand-mint" />,
          },
          {
            title: 'Workflows Run',
            value: jobsCount.toLocaleString(),
            change: `${jobsCount} completed`,
            changeType: jobsCount > 0 ? 'positive' : 'neutral',
            icon: <GitBranch className="h-5 w-5 text-purple-400" />,
          },
          {
            title: 'Chat Sessions',
            value: chatCount.toLocaleString(),
            change: `${chatCount} sessions`,
            changeType: chatCount > 0 ? 'positive' : 'neutral',
            icon: <MessageSquare className="h-5 w-5 text-amber-400" />,
          },
        ]);
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
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="dashboard-card animate-pulse">
            <div className="h-4 bg-white/10 rounded w-1/2 mb-4"></div>
            <div className="h-8 bg-white/10 rounded w-3/4"></div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {cards.map((card, index) => (
        <div key={index} className="dashboard-card">
          <div className="flex items-center justify-between">
            <h3 className="font-heading text-sm font-medium text-brand-silver/70">{card.title}</h3>
            {card.icon}
          </div>
          <div className="mt-2 flex items-baseline">
            <p className="text-2xl font-heading font-semibold text-white">{card.value}</p>
            <p
              className={`ml-2 text-sm ${
                card.changeType === 'positive'
                  ? 'text-brand-mint'
                  : 'text-brand-silver/70'
              }`}
            >
              {card.change}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}