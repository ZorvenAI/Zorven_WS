/**
 * Orchestration API helpers.
 *
 * Wraps apiClient for the /orchestration/ endpoints and returns
 * typed responses.  All functions throw on network/HTTP errors so
 * callers can handle them uniformly.
 */

import { apiClient } from '@/lib/api';
import type {
  AnalysisJob,
  CreateJobPayload,
  ManifestGraphData,
  PipelineManifest,
  PipelineManifestListItem,
} from '@/types/orchestration';

const BASE = '/orchestration';

/** DRF paginated response envelope */
interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body}`);
  }
  return response.json() as Promise<T>;
}

/**
 * Parse a DRF response that may be paginated (object with `results`)
 * or a plain array.  Returns the items array either way.
 */
async function parseList<T>(response: Response): Promise<T[]> {
  const data = await parseOrThrow<PaginatedResponse<T> | T[]>(response);
  if (Array.isArray(data)) return data;
  return data.results;
}

// ── Jobs ──

export async function listJobs(): Promise<AnalysisJob[]> {
  const res = await apiClient.get(`${BASE}/jobs/`);
  return parseList<AnalysisJob>(res);
}

export async function getJob(jobId: string): Promise<AnalysisJob> {
  const res = await apiClient.get(`${BASE}/jobs/${jobId}/`);
  return parseOrThrow<AnalysisJob>(res);
}

export async function createJob(data: CreateJobPayload): Promise<AnalysisJob> {
  const res = await apiClient.post(`${BASE}/jobs/`, data);
  return parseOrThrow<AnalysisJob>(res);
}

export async function cancelJob(jobId: string): Promise<{ status: string }> {
  const res = await apiClient.post(`${BASE}/jobs/${jobId}/cancel/`, {});
  return parseOrThrow<{ status: string }>(res);
}

// ── Manifests ──

export async function listManifests(): Promise<PipelineManifestListItem[]> {
  const res = await apiClient.get(`${BASE}/manifests/`);
  return parseList<PipelineManifestListItem>(res);
}

export async function getManifest(id: number): Promise<PipelineManifest> {
  const res = await apiClient.get(`${BASE}/manifests/${id}/`);
  return parseOrThrow<PipelineManifest>(res);
}

/**
 * Fetch the manifest_data graph for a given manifest ID.
 * Returns null if the manifest does not have graph data.
 */
export async function getManifestGraphData(
  manifestId: number,
): Promise<ManifestGraphData | null> {
  try {
    const manifest = await getManifest(manifestId);
    const data = manifest.manifest_data;
    if (
      data &&
      typeof data === 'object' &&
      'nodes' in data &&
      Array.isArray(data.nodes)
    ) {
      return data as unknown as ManifestGraphData;
    }
    return null;
  } catch {
    return null;
  }
}
