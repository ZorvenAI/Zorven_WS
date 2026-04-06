import { apiClient } from '@/lib/api';
import type {
  CampaignRegistry,
  OptimizationRecommendation,
  OptimizationAction,
  CampaignSettings,
} from '@/types/optimization';

const BASE = '/optimization';

/**
 * Normalize a CampaignRegistry object from the API so every consumer gets
 * guaranteed-safe defaults. Django may return null for JSONField/DecimalField
 * values and optional FKs.
 */
function normalizeCampaign(
  raw: Partial<CampaignRegistry> | null | undefined
): CampaignRegistry {
  const c = (raw ?? {}) as Partial<CampaignRegistry>;
  return {
    id: c.id ?? 0,
    campaign_id: c.campaign_id ?? '',
    meta_campaign_id: c.meta_campaign_id ?? '',
    meta_ad_account_id: c.meta_ad_account_id ?? '',
    campaign_name: c.campaign_name ?? '',
    objective: c.objective ?? '',
    status: c.status ?? 'active',
    optimization_mode: c.optimization_mode ?? 'manual',
    target_cpa_usd: c.target_cpa_usd ?? null,
    target_roas: c.target_roas ?? null,
    daily_budget_usd: c.daily_budget_usd ?? 0,
    lifetime_budget_usd: c.lifetime_budget_usd ?? null,
    ad_sets: Array.isArray(c.ad_sets) ? c.ad_sets : [],
    ads: Array.isArray(c.ads) ? c.ads : [],
    start_date: c.start_date ?? '',
    end_date: c.end_date ?? null,
    guardrail_config:
      c.guardrail_config && typeof c.guardrail_config === 'object'
        ? c.guardrail_config
        : {},
    source_job_id: c.source_job_id ?? null,
    brand_context_id: c.brand_context_id ?? '',
    sandbox_mode: c.sandbox_mode ?? false,
    age_days: c.age_days ?? 0,
    pending_recommendations_count: c.pending_recommendations_count ?? 0,
    created_at: c.created_at ?? '',
    updated_at: c.updated_at ?? '',
  };
}

function normalizeRecommendation(
  raw: Partial<OptimizationRecommendation> | null | undefined
): OptimizationRecommendation {
  const r = (raw ?? {}) as Partial<OptimizationRecommendation>;
  return {
    ...(r as OptimizationRecommendation),
    current_values: r.current_values ?? {},
    proposed_values: r.proposed_values ?? {},
    projected_impact: r.projected_impact ?? {},
    modified_values: r.modified_values ?? {},
    guardrails_applied: Array.isArray(r.guardrails_applied)
      ? r.guardrails_applied
      : [],
  };
}

function normalizeAction(
  raw: Partial<OptimizationAction> | null | undefined
): OptimizationAction {
  const a = (raw ?? {}) as Partial<OptimizationAction>;
  return {
    ...(a as OptimizationAction),
    old_value: a.old_value ?? {},
    new_value: a.new_value ?? {},
    meta_api_response: a.meta_api_response ?? {},
    verification_result: a.verification_result ?? {},
    guardrails_applied: Array.isArray(a.guardrails_applied)
      ? a.guardrails_applied
      : [],
  };
}

export async function fetchCampaigns(): Promise<CampaignRegistry[]> {
  const response = await apiClient.get(`${BASE}/campaigns/`);
  if (!response.ok) throw new Error('Failed to fetch campaigns');
  const data = await response.json();
  const list = Array.isArray(data) ? data : data.results ?? [];
  return list.map(normalizeCampaign);
}

export async function fetchCampaign(
  campaignId: string
): Promise<CampaignRegistry> {
  const response = await apiClient.get(
    `${BASE}/campaigns/${campaignId}/`
  );
  if (!response.ok) throw new Error('Failed to fetch campaign');
  return normalizeCampaign(await response.json());
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
  const list = Array.isArray(data) ? data : data.results ?? [];
  return list.map(normalizeRecommendation);
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
  const list = Array.isArray(data) ? data : data.results ?? [];
  return list.map(normalizeAction);
}

export async function triggerOptimizationTick(
  campaignId: string
): Promise<{
  triggered: boolean;
  coa_response?: {
    tick_id?: string;
    status?: string;
    campaigns_processed?: number;
    recommendations_generated?: number;
    actions_executed?: number;
    campaign_results?: Array<{
      campaign_id?: string;
      status?: string;
      reasons?: string[];
    }>;
    elapsed_ms?: number;
  };
  error?: string;
}> {
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
  return normalizeCampaign(await response.json());
}
