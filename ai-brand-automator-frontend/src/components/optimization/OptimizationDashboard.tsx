'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Activity } from 'lucide-react';
import type {
  CampaignRegistry,
  OptimizationRecommendation,
  OptimizationAction,
} from '@/types/optimization';
import {
  fetchCampaigns,
  fetchRecommendations,
  fetchActions,
} from '@/lib/optimization';
import CampaignSelector from './CampaignSelector';
import CampaignMetricsCard from './CampaignMetricsCard';
import RecommendationsList from './RecommendationsList';
import RecentActionsList from './RecentActionsList';
import OptimizationSettings from './OptimizationSettings';
import CampaignPerformanceChart from './CampaignPerformanceChart';

const POLL_INTERVAL_MS = 30_000;

export default function OptimizationDashboard() {
  const [campaigns, setCampaigns] = useState<CampaignRegistry[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(
    null
  );
  const [recommendations, setRecommendations] = useState<
    OptimizationRecommendation[]
  >([]);
  const [actions, setActions] = useState<OptimizationAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selectedCampaign = campaigns.find(
    (c) => c.campaign_id === selectedCampaignId
  );

  // Load campaigns on mount
  const loadCampaigns = useCallback(async () => {
    try {
      const data = await fetchCampaigns();
      setCampaigns(data);
      if (data.length > 0 && !selectedCampaignId) {
        setSelectedCampaignId(data[0].campaign_id);
      }
    } catch (err) {
      setCampaigns([]);
      console.error('Failed to load campaigns:', err);
      setError('Failed to load campaigns');
    }
  }, [selectedCampaignId]);

  // Load campaign detail data
  const loadCampaignData = useCallback(async () => {
    if (!selectedCampaignId) return;
    try {
      const [recs, acts] = await Promise.all([
        fetchRecommendations(selectedCampaignId, 'pending'),
        fetchActions(selectedCampaignId),
      ]);
      setRecommendations(recs);
      setActions(acts);
      setError(null);
    } catch (err) {
      setRecommendations([]);
      setActions([]);
      console.error('Failed to load campaign data:', err);
    }
  }, [selectedCampaignId]);

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await loadCampaigns();
      setLoading(false);
    };
    init();
  }, [loadCampaigns]);

  // Load detail data when campaign changes
  useEffect(() => {
    if (selectedCampaignId) {
      loadCampaignData();
    }
  }, [selectedCampaignId, loadCampaignData]);

  // Polling with setTimeout (not setInterval)
  useEffect(() => {
    const poll = async () => {
      if (selectedCampaignId) {
        await loadCampaignData();
      }
      timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
    };
    timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [selectedCampaignId, loadCampaignData]);

  const handleCampaignChange = (campaignId: string) => {
    setSelectedCampaignId(campaignId);
    setRecommendations([]);
    setActions([]);
  };

  const handleRecommendationUpdate = () => {
    loadCampaignData();
    loadCampaigns();
  };

  const handleSettingsUpdate = (updatedCampaign: CampaignRegistry) => {
    setCampaigns((prev) =>
      prev.map((c) =>
        c.campaign_id === updatedCampaign.campaign_id ? updatedCampaign : c
      )
    );
  };

  // Empty state
  if (!loading && campaigns.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <Activity className="h-12 w-12 text-brand-silver/50 mx-auto mb-4" />
        <h2 className="text-lg text-white font-medium mb-2">
          No campaigns registered
        </h2>
        <p className="text-brand-silver text-sm mb-4">
          Publish a campaign through the Ad Publishing workflow to see it here
        </p>
      </div>
    );
  }

  if (error && campaigns.length === 0) {
    return (
      <div className="glass-card p-12 text-center">
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Campaign selector */}
      <CampaignSelector
        campaigns={campaigns}
        selectedId={selectedCampaignId}
        onChange={handleCampaignChange}
        loading={loading}
      />

      {/* Metrics cards */}
      {selectedCampaign && (
        <CampaignMetricsCard campaign={selectedCampaign} />
      )}

      {/* Performance chart */}
      {selectedCampaign && <CampaignPerformanceChart />}

      {/* Two-column layout: Recommendations + Settings */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <RecommendationsList
            campaignId={selectedCampaignId}
            recommendations={recommendations}
            onUpdate={handleRecommendationUpdate}
          />
        </div>
        <div className="lg:col-span-1">
          {selectedCampaign && (
            <OptimizationSettings
              campaign={selectedCampaign}
              onUpdate={handleSettingsUpdate}
            />
          )}
        </div>
      </div>

      {/* Recent actions */}
      <RecentActionsList actions={actions} />
    </div>
  );
}
