'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
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
  const [loading, setLoading] = useState(true); // Start with loading true for initial load
  const [error, setError] = useState<string | null>(null);

  // Use refs to avoid recreating callbacks/intervals
  const assetsRef = useRef<BrandAsset[]>([]);
  const isPollingRef = useRef(false);
  const initialFetchStartedRef = useRef(false);

  // Keep ref in sync with state
  useEffect(() => {
    assetsRef.current = assets;
  }, [assets]);

  // Core fetch function - silent parameter controls loading indicator
  const doFetch = useCallback(async (silent: boolean) => {
    // Only set loading for initial load (when we have no assets yet)
    if (!silent && assets.length === 0) {
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
      const newAssets = data.results || [];
      
      // Only update state if data has actually changed (prevents unnecessary re-renders)
      const hasChanged = JSON.stringify(newAssets) !== JSON.stringify(assetsRef.current);
      if (hasChanged) {
        setAssets(newAssets);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load assets';
      setError(message);
      console.error('Error fetching assets:', err);
    } finally {
      // Always set loading to false after any fetch
      setLoading(false);
    }
  }, [statusFilter, assets.length]);

  const retryPipeline = useCallback(async (assetId: number): Promise<boolean> => {
    try {
      const response = await apiClient.post(`/assets/${assetId}/retry_pipeline/`, {});

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to retry pipeline');
      }

      // Refresh assets after retry (silent)
      await doFetch(true);
      return true;
    } catch (err) {
      console.error('Error retrying pipeline:', err);
      return false;
    }
  }, [doFetch]);

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

  // Auto-fetch on mount (shows loading) - only once
  useEffect(() => {
    if (autoFetch && !initialFetchStartedRef.current) {
      initialFetchStartedRef.current = true;
      doFetch(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFetch]); // Intentionally exclude doFetch to prevent re-fetching

  // Polling for status updates (silent refresh - no loading indicator)
  useEffect(() => {
    if (pollingInterval <= 0) return;

    const interval = setInterval(() => {
      // Only poll if there are pending/processing assets (use ref to avoid re-creating interval)
      const hasPending = assetsRef.current.some(
        (a) => a.pipeline_status === 'pending' || a.pipeline_status === 'ingested' || a.pipeline_status === 'curated'
      );

      if (hasPending && !isPollingRef.current) {
        isPollingRef.current = true;
        doFetch(true).finally(() => {
          isPollingRef.current = false;
        });
      }
    }, pollingInterval);

    return () => clearInterval(interval);
  }, [pollingInterval, doFetch]);

  const hasPendingAssets = assets.some(
    (a) => a.pipeline_status === 'pending' || a.pipeline_status === 'ingested' || a.pipeline_status === 'curated'
  );

  // Manual refresh shows loading indicator
  const refresh = useCallback(() => {
    return doFetch(false);
  }, [doFetch]);

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
