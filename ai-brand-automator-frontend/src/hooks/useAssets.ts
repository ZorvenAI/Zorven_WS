'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api';
import { BrandAsset, AssetsListResponse, PipelineStatus } from '@/types/assets';

interface UseAssetsOptions {
  /** Auto-fetch on mount */
  autoFetch?: boolean;
  /** Polling interval in ms (0 to disable) */
  pollingInterval?: number;
  /** Filter by pipeline status */
  statusFilter?: PipelineStatus;
}

interface UseAssetsReturn {
  assets: BrandAsset[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  retryPipeline: (assetId: number) => Promise<boolean>;
  deleteAsset: (assetId: number) => Promise<boolean>;
  hasPendingAssets: boolean;
}

/**
 * Custom hook for managing brand assets with optional polling
 */
export function useAssets(options: UseAssetsOptions = {}): UseAssetsReturn {
  const { autoFetch = true, pollingInterval = 0, statusFilter } = options;

  const [assets, setAssets] = useState<BrandAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  const fetchAssets = useCallback(async (showLoading = true) => {
    // Only show loading spinner on initial load, not on polling refreshes
    if (showLoading && isInitialLoad) {
      setLoading(true);
    }
    setError(null);

    try {
      let url = '/assets/';
      if (statusFilter) {
        url += `?pipeline_status=${statusFilter}`;
      }

      const response = await apiClient.get(url);

      if (!response.ok) {
        throw new Error('Failed to fetch assets');
      }

      const data: AssetsListResponse = await response.json();
      setAssets(data.results || []);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load assets';
      setError(message);
      console.error('Error fetching assets:', err);
    } finally {
      setLoading(false);
      setIsInitialLoad(false);
    }
  }, [statusFilter, isInitialLoad]);

  const retryPipeline = useCallback(async (assetId: number): Promise<boolean> => {
    try {
      const response = await apiClient.post(`/assets/${assetId}/retry_pipeline/`, {});

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to retry pipeline');
      }

      // Refresh assets after retry
      await fetchAssets();
      return true;
    } catch (err) {
      console.error('Error retrying pipeline:', err);
      return false;
    }
  }, [fetchAssets]);

  const deleteAsset = useCallback(async (assetId: number): Promise<boolean> => {
    try {
      const response = await apiClient.delete(`/assets/${assetId}/`);

      if (!response.ok) {
        throw new Error('Failed to delete asset');
      }

      // Remove from local state
      setAssets((prev) => prev.filter((a) => a.id !== assetId));
      return true;
    } catch (err) {
      console.error('Error deleting asset:', err);
      return false;
    }
  }, []);

  // Auto-fetch on mount
  useEffect(() => {
    if (autoFetch) {
      fetchAssets(true);
    }
  }, [autoFetch, fetchAssets]);

  // Polling for status updates (silent refresh - no loading indicator)
  useEffect(() => {
    if (pollingInterval <= 0) return;

    const interval = setInterval(() => {
      // Only poll if there are pending/processing assets
      const hasPending = assets.some(
        (a) => a.pipeline_status === 'pending' || a.pipeline_status === 'ingested' || a.pipeline_status === 'curated'
      );

      if (hasPending) {
        fetchAssets(false); // Silent refresh - no loading indicator
      }
    }, pollingInterval);

    return () => clearInterval(interval);
  }, [pollingInterval, assets, fetchAssets]);

  const hasPendingAssets = assets.some(
    (a) => a.pipeline_status === 'pending' || a.pipeline_status === 'ingested' || a.pipeline_status === 'curated'
  );

  // Manual refresh always shows loading
  const refresh = useCallback(() => {
    setLoading(true);
    return fetchAssets(true);
  }, [fetchAssets]);

  return {
    assets,
    loading,
    error,
    refresh,
    retryPipeline,
    deleteAsset,
    hasPendingAssets,
  };
}

/**
 * Upload a file and return the created asset
 */
export async function uploadAsset(file: File, fileType: string): Promise<BrandAsset> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('file_type', fileType);

  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/assets/upload/`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${localStorage.getItem('access_token')}`,
      },
      body: formData,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || error.message || 'Upload failed');
  }

  return response.json();
}
