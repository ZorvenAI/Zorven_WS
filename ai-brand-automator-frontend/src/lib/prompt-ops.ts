import type {
  CanaryDeployment,
  CanaryHistoryEntry,
  CanaryMetricsComparison,
} from '@/types/prompt-ops';

const getBaseUrl = (): string => {
  if (process.env.NEXT_PUBLIC_PROMPT_OPS_API_URL) {
    return process.env.NEXT_PUBLIC_PROMPT_OPS_API_URL;
  }
  // Default to same host, port 8110 (prompt-optimization-svc)
  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8110`;
  }
  return 'http://localhost:8110';
};

async function fetchJson<T>(path: string): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`Prompt Ops API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function getActiveCanaries(): Promise<CanaryDeployment[]> {
  const data = await fetchJson<{ canaries: CanaryDeployment[] }>(
    '/v1/canary/active'
  );
  return data.canaries;
}

export async function getCanaryMetrics(
  promptName: string
): Promise<CanaryMetricsComparison> {
  return fetchJson<CanaryMetricsComparison>(
    `/v1/canary/${encodeURIComponent(promptName)}/metrics`
  );
}

export async function getCanaryHistory(): Promise<CanaryHistoryEntry[]> {
  const data = await fetchJson<{ history: CanaryHistoryEntry[] }>(
    '/v1/canary/history'
  );
  return data.history;
}
