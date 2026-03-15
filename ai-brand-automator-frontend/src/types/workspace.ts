/**
 * TypeScript types for the workspace (workflow management) feature.
 *
 * Maps 1-to-1 with the DRF serializers in
 * ai-brand-automator/workspace/serializers.py
 */

import type { JobStatus, ManifestGraphData } from './orchestration';

// ── Workflow ──

export type WorkflowSource = 'created' | 'cloned' | 'template' | 'chat';

export interface UserWorkflowSummary {
  id: number;
  workflow_id: string;
  name: string;
  description: string;
  source: WorkflowSource;
  is_favorite: boolean;
  execution_count: number;
  last_executed_at: string | null;
  last_job_status: JobStatus | null;
  created_at: string;
  updated_at: string;
}

export interface UserWorkflowDetail extends UserWorkflowSummary {
  manifest: number;
  manifest_data: ManifestGraphData | null;
  layout_data: LayoutData;
  created_by_email: string | null;
  /** job_id (UUID) of the most recent execution, if any. */
  last_job_id: string | null;
}

// ── Layout ──

export interface NodePosition {
  x: number;
  y: number;
}

export interface ViewportState {
  x: number;
  y: number;
  zoom: number;
}

export interface LayoutData {
  nodes: Record<string, NodePosition>;
  viewport: ViewportState;
}

// ── Snapshot ──

export interface WorkflowSnapshot {
  id: number;
  snapshot_id: string;
  job_id: string;
  job_status: JobStatus;
  summary: Record<string, unknown>;
  dashboard_data: DashboardData;
  duration_seconds: number | null;
  chat_session_id: string | null;
  created_at: string;
}

// ── Dashboard Data ──

export interface DashboardTypedData {
  voc_health_score?: number;
  nps?: number;
  sentiment_trend?: string;
  trends_identified?: number;
  pain_points_count?: number;
  data_coverage_pct?: number;
  confidence_score?: number;
}

export interface DashboardData {
  typed: DashboardTypedData;
  generic: Record<string, unknown>;
}

// ── Agent Catalog ──

export type AgentHealth = 'healthy' | 'unhealthy' | 'unknown';

export interface AgentCatalogEntry {
  id: string;
  name: string;
  label: string;
  description: string;
  type: 'internal' | 'external';
  url?: string;
  handler?: string;
  health: AgentHealth;
  icon?: string;
}

// ── Request Payloads ──

export interface CreateWorkflowPayload {
  name: string;
  description?: string;
  manifest_data: ManifestGraphData;
  layout_data?: LayoutData;
}

export interface UpdateWorkflowPayload {
  name?: string;
  description?: string;
  manifest_data?: ManifestGraphData;
  layout_data?: LayoutData;
  is_favorite?: boolean;
}

export interface ExecuteWorkflowPayload {
  input_prompt: string;
  input_context?: Record<string, unknown>;
}

export interface CloneWorkflowPayload {
  name: string;
}

export interface ImportWorkflowPayload {
  name: string;
  description?: string;
  manifest_data: ManifestGraphData;
  layout_data?: LayoutData;
}

export interface LinkFromChatPayload {
  job_id: string;
  chat_session_id: string;
}

export interface LinkFromChatResponse {
  workflow_id: string;
  snapshot_id: string | null;
}

// ── Lock ──

export interface LockInfo {
  locked: boolean;
  locked_by?: string;
  acquired_at?: string;
  is_mine?: boolean;
}

export interface LockAcquireResponse {
  status: 'acquired' | 'locked';
  locked_by?: string;
  acquired_at?: string;
}

// ── Export ──

export interface WorkflowExportData {
  name: string;
  description: string;
  manifest_data: ManifestGraphData;
  layout_data: LayoutData;
  source: WorkflowSource;
  exported_at: string;
}
