/**
 * TypeScript types for the Continuous Optimization Agent feature.
 *
 * Maps to the DRF serializers in
 * ai-brand-automator/optimization/serializers.py
 */

export interface AdSetEntry {
  id: string;
  name: string;
  status: string;
  targeting: Record<string, unknown>;
  daily_budget: number;
}

export interface AdEntry {
  id: string;
  ad_set_id: string;
  name: string;
  status: string;
  creative_id: string;
}

export interface CampaignRegistry {
  id: number;
  campaign_id: string;
  meta_campaign_id: string;
  meta_ad_account_id: string;
  campaign_name: string;
  objective: string;
  status: 'active' | 'paused' | 'completed' | 'archived';
  optimization_mode: 'manual' | 'autonomous';
  // Django DecimalField is serialized as a string over the wire
  target_cpa_usd: number | string | null;
  target_roas: number | string | null;
  daily_budget_usd: number | string;
  lifetime_budget_usd: number | string | null;
  ad_sets: AdSetEntry[];
  ads: AdEntry[];
  start_date: string;
  end_date: string | null;
  guardrail_config: Record<string, unknown> | null;
  source_job_id: string | null;
  brand_context_id: string;
  sandbox_mode: boolean;
  age_days: number;
  pending_recommendations_count: number;
  created_at: string;
  updated_at: string;
}

export interface OptimizationRecommendation {
  id: number;
  recommendation_id: string;
  campaign: number;
  campaign_name: string;
  action_type:
    | 'PAUSE'
    | 'SCALE'
    | 'REALLOCATE'
    | 'REFRESH'
    | 'ADJUST_BID'
    | 'ADJUST_PLACEMENT'
    | 'ADJUST_SCHEDULE'
    | 'ACTIVATE';
  entity_type: 'campaign' | 'ad_set' | 'ad';
  entity_id: string;
  current_values: Record<string, unknown>;
  proposed_values: Record<string, unknown>;
  rationale: string;
  projected_impact: Record<string, unknown>;
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  status:
    | 'pending'
    | 'approved'
    | 'rejected'
    | 'modified'
    | 'expired'
    | 'executed';
  approved_by: string;
  rejection_reason: string;
  modified_values: Record<string, unknown>;
  expires_at: string;
  executed_at: string | null;
  tick_id: string;
  data_freshness: string;
  guardrails_applied: string[];
  is_expired: boolean;
  created_at: string;
  updated_at: string;
}

export interface OptimizationAction {
  id: number;
  action_id: string;
  campaign: number;
  campaign_name: string;
  recommendation: number | null;
  action_type: string;
  entity_type: string;
  entity_id: string;
  old_value: Record<string, unknown>;
  new_value: Record<string, unknown>;
  mode: 'manual' | 'autonomous';
  rationale: string;
  guardrails_applied: string[];
  meta_api_response: Record<string, unknown>;
  verified: boolean;
  verification_result: Record<string, unknown>;
  executed_at: string;
}

export interface CampaignSettings {
  optimization_mode?: 'manual' | 'autonomous';
  guardrail_config?: Record<string, unknown>;
}
