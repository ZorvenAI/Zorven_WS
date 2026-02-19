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

// ── Log Console ──

export interface LogEntry {
  timestamp: string;
  nodeId: string;
  message: string;
  level: 'info' | 'success' | 'error';
}
