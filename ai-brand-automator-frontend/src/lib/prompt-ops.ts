import type {
  CanaryDeployment,
  CanaryHistoryEntry,
  CanaryMetricsComparison,
  OptimizationRun,
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

export async function getOptimizationRuns(): Promise<OptimizationRun[]> {
  const data = await fetchJson<{ runs: OptimizationRun[] }>(
    '/v1/optimize/runs'
  );
  return data.runs;
}

export async function triggerOptimization(
  groupName: string
): Promise<{ status: string; task_id: string }> {
  const url = `${getBaseUrl()}/v1/optimize`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Role': 'admin',
    },
    body: JSON.stringify({
      input_prompt: `Optimize ${groupName}`,
      config: { group_name: groupName },
    }),
  });
  if (!res.ok) {
    throw new Error(`Optimize trigger failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}
