'use client';

import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api';

interface Activity {
  id: string;
  action: string;
  timestamp: string;
  type: string;
}

interface ApiGeneration {
  id: string | number;
  generation_type?: string;
  created_at: string;
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

export default function RecentActivity() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);

  const formatTimestamp = (timestamp: string): string => {
    if (!timestamp) return 'Unknown';
    
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 60) return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} ago`;
    if (hours < 24) return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`;
    if (days < 7) return `${days} ${days === 1 ? 'day' : 'days'} ago`;
    
    return date.toLocaleDateString();
  };

  useEffect(() => {
    const fetchActivities = async () => {
      try {
        // Fetch AI generations (most recent activity)
        const aiGenerationsResponse = await apiClient.get('/ai/generations/');
        const aiGenerations = await aiGenerationsResponse.json();
        
        // Fetch assets
        const assetsResponse = await apiClient.get('/assets/');
        const assets = await assetsResponse.json();

        // Fetch companies
        const companiesResponse = await apiClient.get('/companies/');
        const companies = await companiesResponse.json();

        // Combine and format activities
        const allActivities: Activity[] = [];

        // Add AI generations
        if (aiGenerations && Array.isArray(aiGenerations)) {
          aiGenerations.slice(0, 5).forEach((gen: ApiGeneration) => {
            allActivities.push({
              id: `ai-${gen.id}`,
              action: `AI generated ${gen.generation_type || 'content'}`,
              timestamp: formatTimestamp(gen.created_at),
              type: 'ai',
            });
          });
        }

        // Add asset uploads
        if (assets && Array.isArray(assets)) {
          assets.slice(0, 3).forEach((asset: ApiAsset) => {
            allActivities.push({
              id: `asset-${asset.id}`,
              action: `Uploaded ${asset.asset_type || 'asset'}: ${asset.file_name || 'file'}`,
              timestamp: formatTimestamp(asset.uploaded_at),
              type: 'upload',
            });
          });
        }

        // Add company updates
        if (companies && Array.isArray(companies)) {
          companies.slice(0, 2).forEach((company: ApiCompany) => {
            allActivities.push({
              id: `company-${company.id}`,
              action: `Updated company profile: ${company.name}`,
              timestamp: formatTimestamp(company.updated_at || company.created_at),
              type: 'update',
            });
          });
        }

        // Sort by timestamp (most recent first) and take top 5
        allActivities.sort((a, b) => {
          return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
        });

        setActivities(allActivities.slice(0, 5));
        setLoading(false);
      } catch (error) {
        console.error('Error fetching activities:', error);
        setLoading(false);
      }
    };
    
    fetchActivities();
  }, []);


  if (loading) {
    return (
      <div className="dashboard-card">
        <div className="mb-4">
          <h3 className="text-lg font-heading font-medium text-white">Recent Activity</h3>
        </div>
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="animate-pulse">
              <div className="h-4 bg-white/10 rounded w-3/4 mb-2"></div>
              <div className="h-3 bg-white/10 rounded w-1/4"></div>
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
          <h3 className="text-lg font-heading font-medium text-white">Recent Activity</h3>
        </div>
        <div className="py-8 text-center">
          <p className="text-brand-silver/70">No recent activity yet. Start by creating a company or uploading assets!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-card">
      <div className="mb-4">
        <h3 className="text-lg font-heading font-medium text-white">Recent Activity</h3>
      </div>
      <div className="space-y-3">
        {activities.map((activity) => (
          <div key={activity.id} className="py-3 border-b border-white/10 last:border-0">
            <div className="flex items-center justify-between">
              <p className="text-sm text-white">{activity.action}</p>
              <p className="text-sm text-brand-silver/50">{activity.timestamp}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}