export interface CanaryDeployment {
  prompt_name: string;
  canary_version: number;
  production_version: number;
  agent_code: string;
  started_at: string;
  expires_at: string;
  time_remaining_hours: number;
  active: boolean;
}

export interface CanaryMetricsComparison {
  prompt_name: string;
  canary_version: number;
  production_version: number;
  canary_metrics: Record<string, number>;
  production_metrics: Record<string, number>;
  regression_pct: number | null;
  status: 'healthy' | 'warning' | 'regressed';
}

export interface CanaryHistoryEntry {
  prompt_name: string;
  canary_version: number;
  started_at: string;
  ended_at: string;
  outcome: 'promoted' | 'rolled_back' | 'expired';
  final_regression_pct: number | null;
}
