/**
 * TypeScript types for the orchestration (pipeline) feature.
 *
 * Maps 1-to-1 with the DRF serializers in
 * ai-brand-automator/orchestration/serializers.py
 */

// ── Agent-level progress reported by pipeline-orchestrator-svc ──

export interface AgentProgress {
  status: 'pending' | 'running' | 'done' | 'failed';
  output?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
}

// ── Pipeline Manifest (HLD v6.0 Pipeline-as-Code) ──

export interface PipelineManifest {
  id: number;
  pipeline_id: string;
  name: string;
  description: string;
  manifest_data: Record<string, unknown>;
  version: number;
  is_active: boolean;
  created_by_email?: string;
  created_at: string;
  updated_at: string;
}

/** Lightweight shape returned by the list endpoint (no manifest_data). */
export interface PipelineManifestListItem {
  id: number;
  pipeline_id: string;
  name: string;
  description: string;
  version: number;
  is_active: boolean;
  updated_at: string;
}

// ── Analysis Job ──

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface AnalysisJob {
  id: number;
  job_id: string;
  manifest: number | null;
  manifest_name: string | null;
  input_prompt: string;
  input_context: Record<string, unknown>;
  status: JobStatus;
  progress: Record<string, AgentProgress>;
  result_data: Record<string, unknown> | null;
  error_message: string;
  created_by_email: string;
  duration_seconds: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Lightweight response from the /quick-status endpoint (Redis-cached). */
export interface QuickStatus {
  status: JobStatus;
  progress: Record<string, AgentProgress>;
  current_node: string | null;
  progress_percent: number;
  last_thought: string | null;
  result_data?: Record<string, unknown>;
  manifest_name?: string | null;
  error_message?: string;
}

// ── Request payloads ──

export interface CreateJobPayload {
  manifest?: number | null;
  input_prompt: string;
  input_context?: Record<string, unknown>;
}

// ── Manifest Graph Types (for React Flow visualization) ──

export interface ManifestNode {
  id: string;
  type: 'internal' | 'external';
  handler?: string;
  url?: string;
  label?: string;
}

export interface ManifestGraphData {
  nodes: ManifestNode[];
  edges: [string, string][];
  global_config?: Record<string, unknown>;
}

// ── Audience Persona Types ──

export interface DemographicProfile {
  segment_label: string;
  age_range?: string;
  gender_distribution?: Record<string, number>;
  income_range?: string;
  education_level?: string;
  job_titles?: string[];
  company_size?: string;
  industry_verticals?: string[];
  geographic_distribution?: Record<string, number>;
  confidence_score?: number;
}

export interface PsychographicProfile {
  segment_label: string;
  values?: string[];
  interests?: string[];
  lifestyle?: string;
  personality_traits?: string[];
  media_consumption?: string[];
  decision_style?: string;
  information_sources?: string[];
  technology_adoption?: string;
  brand_affinity_drivers?: string[];
  confidence_score?: number;
}

export interface PersonaProfile {
  slug: string;
  segment_label: string;
  data_source: 'crm_grounded' | 'research_based';
  demographics?: DemographicProfile;
  psychographics?: PsychographicProfile;
  pain_points?: string[];
  motivations?: string[];
  objections?: string[];
  preferred_channels?: string[];
  priority_score?: number;
  confidence_score?: number;
  narrative?: string;
  citations?: string[];
  requires_admin_review?: boolean;
}

export interface JourneyStage {
  name: string;
  description?: string;
  touchpoints?: string[];
  info_needs?: string[];
  emotional_state?: string;
  decision_criteria?: string[];
  objections?: string[];
  content_recommendations?: string[];
  estimated_days?: number;
  key_actions?: string[];
}

export interface BuyingJourneyMap {
  persona_slug: string;
  persona_label: string;
  total_estimated_cycle_days?: number;
  stages: JourneyStage[];
}

// ── Trend & Cultural Insights Types ──

export interface ScoredTrend {
  trend_slug: string;
  topic: string;
  relevance_score: number;
  audience_alignment: number;
  competitive_landscape: number;
  brand_fit: number;
  momentum: number;
  recommendation: 'capitalize' | 'monitor' | 'avoid';
  rationale: string;
  citations: string[];
  platforms: string[];
}

export interface TrendPersonaMapping {
  trend_slug: string;
  persona_slug: string;
  affinity_score: number;
  content_angles: string[];
  customer_segment_overlap: number;
  recommended_channels: string[];
}

export interface TrendPersonaMatrix {
  mappings: TrendPersonaMapping[];
}

export interface OpportunityAlert {
  alert_id: string;
  trend_slug: string;
  relevance_score: number;
  urgency: 'immediate' | 'this_week' | 'this_month';
  recommendation: string;
  affected_personas: string[];
  suggested_response: string;
  expiry_estimate: string;
}

export interface CulturalShift {
  domain: string;
  shift_description: string;
  evidence_strength: number;
  affected_demographics: string[];
  timeline_estimate: string;
  sources: Record<string, string>[];
}

export interface ViralPatternProfile {
  top_formats: string[];
  emotional_triggers: string[];
  amplification_mechanics: string[];
  platform_factors: Record<string, string>[];
  brand_safe_patterns: string[];
  brand_unsafe_patterns: string[];
}

export interface GenerationalProfile {
  generation: string;
  emerging_behaviors: string[];
  language_patterns: string[];
  platform_shifts: string[];
  brand_expectations: string[];
  subcultures: string[];
  relevance_to_personas: string[];
}

export interface SlangTerm {
  term: string;
  definition: string;
  origin_platform: string;
  adoption_stage: string;
  sensitivity_flag: boolean;
}

export interface LanguageTrendProfile {
  emerging_terms: SlangTerm[];
  fading_terms: string[];
  language_shifts: string[];
}

export interface TrendReport {
  executive_summary: string;
  trend_scorecard: ScoredTrend[];
  new_trends: string[];
  rising_trends: string[];
  fading_trends: string[];
  competitive_trend_gaps: string[];
  persona_trend_alignment: TrendPersonaMatrix | null;
  strategic_recommendations: string[];
  confidence_score: number;
  citations: string[];
}

// ── Log Console ──

export interface LogEntry {
  timestamp: string;
  nodeId: string;
  message: string;
  level: 'info' | 'success' | 'error';
}
