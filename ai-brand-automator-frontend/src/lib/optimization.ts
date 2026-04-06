import { apiClient } from '@/lib/api';
import type {
  CampaignRegistry,
  OptimizationRecommendation,
  OptimizationAction,
  CampaignSettings,
} from '@/types/optimization';

const BASE = '/optimization';

export async function fetchCampaigns(): Promise<CampaignRegistry[]> {
  const response = await apiClient.get(`${BASE}/campaigns/`);
  if (!response.ok) throw new Error('Failed to fetch campaigns');
  const data = await response.json();
  return Array.isArray(data) ? data : data.results ?? [];
}

export async function fetchCampaign(
  campaignId: string
): Promise<CampaignRegistry> {
  const response = await apiClient.get(
    `${BASE}/campaigns/${campaignId}/`
  );
  if (!response.ok) throw new Error('Failed to fetch campaign');
  return response.json();
}

export async function fetchRecommendations(
  campaignId: string,
  status?: string
): Promise<OptimizationRecommendation[]> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  const qs = params.toString();
  const response = await apiClient.get(
    `${BASE}/campaigns/${campaignId}/recommendations/${qs ? `?${qs}` : ''}`
  );
  if (!response.ok) throw new Error('Failed to fetch recommendations');
  const data = await response.json();
  return Array.isArray(data) ? data : data.results ?? [];
}

export async function approveRecommendation(
  campaignId: string,
  recId: string,
  modifiedValues?: Record<string, unknown>
): Promise<OptimizationRecommendation> {
  const body: Record<string, unknown> = {};
  if (modifiedValues) body.modified_values = modifiedValues;
  const response = await apiClient.post(
    `${BASE}/campaigns/${campaignId}/recommendations/${recId}/approve/`,
    body
  );
  if (!response.ok) throw new Error('Failed to approve recommendation');
  return response.json();
}

export async function rejectRecommendation(
  campaignId: string,
  recId: string,
  reason?: string
): Promise<OptimizationRecommendation> {
  const body: Record<string, unknown> = {};
  if (reason) body.rejection_reason = reason;
  const response = await apiClient.post(
    `${BASE}/campaigns/${campaignId}/recommendations/${recId}/reject/`,
    body
  );
  if (!response.ok) throw new Error('Failed to reject recommendation');
  return response.json();
}

export async function batchApproveRecommendations(
  campaignId: string
): Promise<{ approved_count: number; expired_count: number }> {
  const response = await apiClient.post(
    `${BASE}/campaigns/${campaignId}/recommendations/batch-approve/`,
    {}
  );
  if (!response.ok) throw new Error('Failed to batch approve');
  return response.json();
}

export async function fetchActions(
  campaignId: string
): Promise<OptimizationAction[]> {
  const response = await apiClient.get(
    `${BASE}/campaigns/${campaignId}/actions/`
  );
  if (!response.ok) throw new Error('Failed to fetch actions');
  const data = await response.json();
  return Array.isArray(data) ? data : data.results ?? [];
}

export async function triggerOptimizationTick(
  campaignId: string
): Promise<{ triggered: boolean; coa_response?: unknown; error?: string }> {
  const response = await apiClient.post(
    `${BASE}/campaigns/${campaignId}/trigger-tick/`,
    {}
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      body.error || `Failed to trigger tick (HTTP ${response.status})`
    );
  }
  return response.json();
}

export async function updateCampaignSettings(
  campaignId: string,
  settings: CampaignSettings
): Promise<CampaignRegistry> {
  const response = await apiClient.patch(
    `${BASE}/campaigns/${campaignId}/settings/`,
    settings
  );
  if (!response.ok) throw new Error('Failed to update campaign settings');
  return response.json();
}
