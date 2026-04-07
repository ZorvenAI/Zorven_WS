import { apiClient } from '@/lib/api';

const BASE = '/intelligence-loop';

export type LearningCategory =
  | 'audience'
  | 'messaging'
  | 'creative'
  | 'funnel'
  | 'competitive';
export type LearningImpact = 'LOW' | 'MEDIUM' | 'HIGH';
export type LearningWorkflow = 'WF1' | 'WF2' | 'WF3';
export type LearningStatus =
  | 'new'
  | 'applied'
  | 'dismissed'
  | 'saved'
  | 'expired';

export interface LearningRecord {
  id: number;
  learning_id: string;
  category: LearningCategory;
  headline: string;
  detail: Record<string, unknown>;
  confidence: number;
  impact: LearningImpact;
  target_workflow: LearningWorkflow;
  target_agent: string;
  status: LearningStatus;
  rag_document_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CampaignIntelligenceList {
  id: number;
  intelligence_id: string;
  campaign: number;
  campaign_name: string;
  mode: 'store_only' | 'auto_trigger';
  trigger_source: string;
  auto_reruns_triggered: number;
  rag_writes: number;
  learnings_count: number;
  high_confidence_count: number;
  brand_context_id: string;
  created_at: string;
}

export interface CampaignIntelligenceDetail extends CampaignIntelligenceList {
  job_id: string;
  intelligence_report: Record<string, unknown>;
  contradictions: Array<Record<string, unknown>>;
  learnings: LearningRecord[];
  updated_at: string;
}

export interface WF2RerunRequest {
  id: number;
  request_id: string;
  learning: number;
  learning_headline: string;
  requested_agent: string;
  rationale: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  decided_by_email: string;
  decided_at: string | null;
  rejection_reason: string;
  expires_at: string;
  is_expired: boolean;
  job_id: string | null;
  created_at: string;
  updated_at: string;
}

async function unwrap<T>(res: Response, label: string): Promise<T> {
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${label} failed (${res.status})${detail ? `: ${detail}` : ''}`);
  }
  return res.json() as Promise<T>;
}

function listFrom<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  const obj = data as { results?: T[] } | null;
  return obj?.results ?? [];
}

export async function fetchIntelligenceReports(
  campaignId?: string
): Promise<CampaignIntelligenceList[]> {
  const qs = campaignId ? `?campaign=${encodeURIComponent(campaignId)}` : '';
  const res = await apiClient.get(`${BASE}/intelligence-reports/${qs}`);
  const data = await unwrap<unknown>(res, 'fetchIntelligenceReports');
  return listFrom<CampaignIntelligenceList>(data);
}

export async function fetchIntelligenceReport(
  intelligenceId: string
): Promise<CampaignIntelligenceDetail> {
  const res = await apiClient.get(
    `${BASE}/intelligence-reports/${intelligenceId}/`
  );
  return unwrap<CampaignIntelligenceDetail>(res, 'fetchIntelligenceReport');
}

export async function applyLearning(
  learningId: string,
  note = ''
): Promise<{ learning_id: string; status: string; job_id: string; pipeline_id: string }> {
  const res = await apiClient.post(`${BASE}/learnings/${learningId}/apply/`, {
    note,
  });
  return unwrap(res, 'applyLearning');
}

export async function dismissLearning(
  learningId: string
): Promise<LearningRecord> {
  const res = await apiClient.post(
    `${BASE}/learnings/${learningId}/dismiss/`,
    {}
  );
  return unwrap<LearningRecord>(res, 'dismissLearning');
}

export async function saveLearning(
  learningId: string
): Promise<LearningRecord> {
  const res = await apiClient.post(
    `${BASE}/learnings/${learningId}/save/`,
    {}
  );
  return unwrap<LearningRecord>(res, 'saveLearning');
}

export async function fetchWF2Requests(
  status?: string
): Promise<WF2RerunRequest[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  const res = await apiClient.get(`${BASE}/wf2-rerun-requests/${qs}`);
  const data = await unwrap<unknown>(res, 'fetchWF2Requests');
  return listFrom<WF2RerunRequest>(data);
}

export async function approveWF2Request(
  requestId: string
): Promise<WF2RerunRequest> {
  const res = await apiClient.post(
    `${BASE}/wf2-rerun-requests/${requestId}/approve/`,
    {}
  );
  return unwrap<WF2RerunRequest>(res, 'approveWF2Request');
}

export async function rejectWF2Request(
  requestId: string,
  reason = ''
): Promise<WF2RerunRequest> {
  const res = await apiClient.post(
    `${BASE}/wf2-rerun-requests/${requestId}/reject/`,
    { reason }
  );
  return unwrap<WF2RerunRequest>(res, 'rejectWF2Request');
}

export async function triggerExtraction(
  campaignId: string,
  mode: 'store_only' | 'auto_trigger' = 'store_only'
): Promise<{ status: string; ila_status_code: number; ila_response: unknown }> {
  const res = await apiClient.post(`${BASE}/trigger/`, {
    campaign_id: campaignId,
    mode,
  });
  return unwrap(res, 'triggerExtraction');
}
