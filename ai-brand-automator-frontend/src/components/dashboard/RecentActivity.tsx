'use client';

import { useState, useEffect } from 'react';
import { MessageSquare, Play, Upload, Building2 } from 'lucide-react';
import { apiClient } from '@/lib/api';

interface Activity {
  id: string;
  action: string;
  timestamp: string;
  rawDate: string;
  type: 'chat' | 'job' | 'upload' | 'company';
}

interface ApiChatSession {
  id: number;
  session_id: string;
  title: string;
  last_activity: string;
}

interface ApiJob {
  id: number;
  job_id: string;
  manifest_name?: string | null;
  input_prompt?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface ApiAsset {
  id: string | number;
  asset_type?: string;
  file_name?: string;
  uploaded_at: string;
}

interface ApiCompany {
  id: string | number;
  name: string;
  created_at: string;
  updated_at?: string;
}

function unwrapPaginated<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && 'results' in data) {
    return (data as { results: T[] }).results ?? [];
  }
  return [];
}

const TYPE_ICONS: Record<Activity['type'], React.ReactNode> = {
  chat: <MessageSquare className="w-4 h-4 text-brand-electric" />,
  job: <Play className="w-4 h-4 text-emerald-400" />,
  upload: <Upload className="w-4 h-4 text-amber-400" />,
  company: <Building2 className="w-4 h-4 text-purple-400" />,
};

function formatTimestamp(timestamp: string): string {
  if (!timestamp) return 'Unknown';

  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - date.getTime();

  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;

  return date.toLocaleDateString();
}

const JOB_STATUS_LABELS: Record<string, string> = {
  completed: 'completed',
  failed: 'failed',
  running: 'is running',
  queued: 'queued',
  awaiting_approval: 'awaiting approval',
};

export default function RecentActivity() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchActivities = async () => {
      try {
        const [sessionsRes, jobsRes, assetsRes, companiesRes] =
          await Promise.allSettled([
            apiClient.get('/ai/chat-sessions/'),
            apiClient.get('/orchestration/jobs/'),
            apiClient.get('/assets/'),
            apiClient.get('/companies/'),
          ]);

        const sessions = unwrapPaginated<ApiChatSession>(
          sessionsRes.status === 'fulfilled'
            ? await sessionsRes.value.json()
            : []
        );
        const jobs = unwrapPaginated<ApiJob>(
          jobsRes.status === 'fulfilled'
            ? await jobsRes.value.json()
            : []
        );
        const assets = unwrapPaginated<ApiAsset>(
          assetsRes.status === 'fulfilled'
            ? await assetsRes.value.json()
            : []
        );
        const companies = unwrapPaginated<ApiCompany>(
          companiesRes.status === 'fulfilled'
            ? await companiesRes.value.json()
            : []
        );

        const allActivities: Activity[] = [];

        // Chat sessions
        sessions.slice(0, 5).forEach((s) => {
          allActivities.push({
            id: `chat-${s.session_id}`,
            action: s.title || 'Chat session',
            timestamp: formatTimestamp(s.last_activity),
            rawDate: s.last_activity,
            type: 'chat',
          });
        });

        // Pipeline jobs
        jobs.slice(0, 5).forEach((j) => {
          const name = j.manifest_name || 'Pipeline';
          const statusLabel = JOB_STATUS_LABELS[j.status] ?? j.status;
          allActivities.push({
            id: `job-${j.job_id}`,
            action: `${name} ${statusLabel}`,
            timestamp: formatTimestamp(j.updated_at || j.created_at),
            rawDate: j.updated_at || j.created_at,
            type: 'job',
          });
        });

        // Asset uploads
        assets.slice(0, 3).forEach((a) => {
          allActivities.push({
            id: `asset-${a.id}`,
            action: `Uploaded ${a.file_name || a.asset_type || 'asset'}`,
            timestamp: formatTimestamp(a.uploaded_at),
            rawDate: a.uploaded_at,
            type: 'upload',
          });
        });

        // Company updates
        companies.slice(0, 2).forEach((c) => {
          const companyDate = c.updated_at || c.created_at;
          allActivities.push({
            id: `company-${c.id}`,
            action: `Company profile: ${c.name}`,
            timestamp: formatTimestamp(companyDate),
            rawDate: companyDate,
            type: 'company',
          });
        });

        allActivities.sort(
          (a, b) =>
            new Date(b.rawDate).getTime() - new Date(a.rawDate).getTime()
        );

        setActivities(allActivities.slice(0, 8));
      } catch (error) {
        console.error('Error fetching activities:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchActivities();
  }, []);

  if (loading) {
    return (
      <div className="dashboard-card">
        <div className="mb-4">
          <h3 className="text-lg font-heading font-medium text-white">
            Recent Activity
          </h3>
        </div>
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="animate-pulse">
              <div className="h-4 bg-white/10 rounded w-3/4 mb-2" />
              <div className="h-3 bg-white/10 rounded w-1/4" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (activities.length === 0) {
    return (
      <div className="dashboard-card">
        <div className="mb-4">
          <h3 className="text-lg font-heading font-medium text-white">
            Recent Activity
          </h3>
        </div>
        <div className="py-8 text-center">
          <p className="text-brand-silver/70">
            No recent activity yet. Start by creating a company or uploading
            assets!
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-card">
      <div className="mb-4">
        <h3 className="text-lg font-heading font-medium text-white">
          Recent Activity
        </h3>
      </div>
      <div className="space-y-1">
        {activities.map((activity) => (
          <div
            key={activity.id}
            className="flex items-center gap-3 py-2.5 border-b border-white/5 last:border-0"
          >
            <span className="flex-shrink-0">{TYPE_ICONS[activity.type]}</span>
            <p className="text-sm text-white truncate flex-1">
              {activity.action}
            </p>
            <p className="text-xs text-brand-silver/50 whitespace-nowrap flex-shrink-0">
              {activity.timestamp}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
