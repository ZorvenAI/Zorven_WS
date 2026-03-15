/**
 * Workspace API helpers.
 *
 * Wraps apiClient for the /workspace/ endpoints and returns
 * typed responses.  All functions throw on network/HTTP errors so
 * callers can handle them uniformly.
 */

import { apiClient } from '@/lib/api';
import type { AnalysisJob } from '@/types/orchestration';
import type { PipelineManifest } from '@/types/orchestration';
import type {
  AgentCatalogEntry,
  CloneWorkflowPayload,
  CreateWorkflowPayload,
  ExecuteWorkflowPayload,
  ImportWorkflowPayload,
  LinkFromChatPayload,
  LinkFromChatResponse,
  LockAcquireResponse,
  LockInfo,
  UpdateWorkflowPayload,
  UserWorkflowDetail,
  UserWorkflowSummary,
  WorkflowExportData,
  WorkflowSnapshot,
} from '@/types/workspace';

const BASE = '/workspace';

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body}`);
  }
  return response.json() as Promise<T>;
}

/** DRF paginated response envelope */
interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

async function parseList<T>(response: Response): Promise<T[]> {
  const data = await parseOrThrow<PaginatedResponse<T> | T[]>(response);
  if (Array.isArray(data)) return data;
  return data.results;
}

// ── Workflows ──

export async function listWorkflows(): Promise<UserWorkflowSummary[]> {
  const res = await apiClient.get(`${BASE}/workflows/`);
  return parseList<UserWorkflowSummary>(res);
}

export async function getWorkflow(
  workflowId: string,
): Promise<UserWorkflowDetail> {
  const res = await apiClient.get(`${BASE}/workflows/${workflowId}/`);
  return parseOrThrow<UserWorkflowDetail>(res);
}

export async function createWorkflow(
  data: CreateWorkflowPayload,
): Promise<UserWorkflowDetail> {
  const res = await apiClient.post(`${BASE}/workflows/`, data);
  return parseOrThrow<UserWorkflowDetail>(res);
}

export async function updateWorkflow(
  workflowId: string,
  data: UpdateWorkflowPayload,
): Promise<UserWorkflowDetail> {
  const res = await apiClient.put(`${BASE}/workflows/${workflowId}/`, data);
  return parseOrThrow<UserWorkflowDetail>(res);
}

export async function patchWorkflow(
  workflowId: string,
  data: Partial<UpdateWorkflowPayload>,
): Promise<UserWorkflowDetail> {
  const res = await apiClient.patch(`${BASE}/workflows/${workflowId}/`, data);
  return parseOrThrow<UserWorkflowDetail>(res);
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  const res = await apiClient.delete(`${BASE}/workflows/${workflowId}/`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
}

// ── Execute ──

export async function executeWorkflow(
  workflowId: string,
  data: ExecuteWorkflowPayload,
): Promise<AnalysisJob> {
  const res = await apiClient.post(
    `${BASE}/workflows/${workflowId}/execute/`,
    data,
  );
  return parseOrThrow<AnalysisJob>(res);
}

// ── Clone ──

export async function cloneWorkflow(
  workflowId: string,
  data: CloneWorkflowPayload,
): Promise<UserWorkflowDetail> {
  const res = await apiClient.post(
    `${BASE}/workflows/${workflowId}/clone/`,
    data,
  );
  return parseOrThrow<UserWorkflowDetail>(res);
}

// ── Export / Import ──

export async function exportWorkflow(
  workflowId: string,
): Promise<WorkflowExportData> {
  const res = await apiClient.post(
    `${BASE}/workflows/${workflowId}/export/`,
    {},
  );
  return parseOrThrow<WorkflowExportData>(res);
}

export async function importWorkflow(
  data: ImportWorkflowPayload,
): Promise<UserWorkflowDetail> {
  const res = await apiClient.post(`${BASE}/workflows/import/`, data);
  return parseOrThrow<UserWorkflowDetail>(res);
}

// ── Snapshots ──

export async function listSnapshots(
  workflowId: string,
): Promise<WorkflowSnapshot[]> {
  const res = await apiClient.get(
    `${BASE}/workflows/${workflowId}/snapshots/`,
  );
  return parseList<WorkflowSnapshot>(res);
}

// ── Agent Catalog ──

export async function listAgents(): Promise<AgentCatalogEntry[]> {
  const res = await apiClient.get(`${BASE}/agents/`);
  return parseOrThrow<AgentCatalogEntry[]>(res);
}

// ── Lock ──

export async function acquireLock(
  workflowId: string,
): Promise<LockAcquireResponse> {
  const res = await apiClient.post(
    `${BASE}/workflows/${workflowId}/lock/`,
    {},
  );
  // 409 means locked by someone else — parse it as success
  if (res.status === 409) {
    return res.json() as Promise<LockAcquireResponse>;
  }
  return parseOrThrow<LockAcquireResponse>(res);
}

export async function releaseLock(workflowId: string): Promise<void> {
  const res = await apiClient.delete(
    `${BASE}/workflows/${workflowId}/lock/`,
  );
  if (!res.ok && res.status !== 403) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
}

export async function getLockInfo(
  workflowId: string,
): Promise<LockInfo> {
  const res = await apiClient.get(
    `${BASE}/workflows/${workflowId}/lock/`,
  );
  return parseOrThrow<LockInfo>(res);
}

// ── Templates ──

export async function listTemplates(): Promise<PipelineManifest[]> {
  const res = await apiClient.get(`${BASE}/workflows/templates/`);
  return parseOrThrow<PipelineManifest[]>(res);
}

// ── Chat Link ──

export async function linkFromChat(
  data: LinkFromChatPayload,
): Promise<LinkFromChatResponse> {
  const res = await apiClient.post(`${BASE}/link-from-chat/`, data);
  return parseOrThrow<LinkFromChatResponse>(res);
}
