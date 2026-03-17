/**
 * ResultsInspector — right panel of the workspace.
 *
 * Tabs: Results | Logs | Properties | History
 *
 * - Results: Renders ResultDashboard for the active job
 * - Logs: Live execution log derived from progress events
 * - Properties: Selected node details
 * - History: WorkflowSnapshot list
 */

'use client';

import { useState, useMemo, useCallback } from 'react';
import {
  BarChart3,
  Terminal,
  Info,
  History,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
  XCircle,
  CalendarClock,
} from 'lucide-react';
import type { AnalysisJob, AgentProgress, LogEntry, QuickStatus } from '@/types/orchestration';
import type { WorkflowSnapshot, UserWorkflowDetail } from '@/types/workspace';
import type { AgentNodeData } from './AgentNode';
import ResultDashboard from '@/components/pipelines/ResultDashboard';
import LogConsole from '@/components/pipelines/LogConsole';
import { listSnapshots } from '@/lib/workspace';
import { getJob } from '@/lib/orchestration';

// ── Types ──

interface ResultsInspectorProps {
  workflowId: string | null;
  activeJobId: string | null;
  quickStatus: QuickStatus | null;
  /** Currently selected node on the canvas. */
  selectedNodeData?: AgentNodeData | null;
  /** Active workflow detail (shown in Properties when no node selected). */
  workflowDetail?: UserWorkflowDetail | null;
}

type TabId = 'results' | 'logs' | 'properties' | 'history';

// ── Status icon helper ──

function JobStatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'running':
      return <Loader2 className="w-3.5 h-3.5 text-brand-electric animate-spin" />;
    case 'completed':
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
    case 'failed':
      return <XCircle className="w-3.5 h-3.5 text-red-400" />;
    case 'queued':
      return <Clock className="w-3.5 h-3.5 text-amber-400" />;
    default:
      return null;
  }
}

// ── Component ──

export default function ResultsInspector({
  workflowId,
  activeJobId,
  quickStatus,
  selectedNodeData,
  workflowDetail,
}: ResultsInspectorProps) {
  const [activeTab, setActiveTab] = useState<TabId>('results');
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [snapshots, setSnapshots] = useState<WorkflowSnapshot[]>([]);
  const [isLoadingJob, setIsLoadingJob] = useState(false);

  // Track previous values using useState (React 19-compliant pattern for
  // adjusting state during render in response to prop changes).
  // See: https://react.dev/reference/react/useState#storing-information-from-previous-renders
  const [prevJobId, setPrevJobId] = useState<string | null>(null);
  const [prevStatus, setPrevStatus] = useState<string | undefined>(undefined);
  const [fetchedTerminalJobId, setFetchedTerminalJobId] = useState<string | null>(null);

  // Reset on job change
  if (activeJobId !== prevJobId) {
    setPrevJobId(activeJobId);
    setPrevStatus(undefined);
    setFetchedTerminalJobId(null);
    setJob(null);
  }

  // Auto-switch tabs + fetch job on status transitions
  const jobStatus = quickStatus?.status;
  if (jobStatus !== prevStatus) {
    setPrevStatus(jobStatus);
    if (jobStatus === 'completed' || jobStatus === 'failed') {
      setActiveTab('results');
      // Fetch full job on terminal status
      if (activeJobId && fetchedTerminalJobId !== activeJobId) {
        setFetchedTerminalJobId(activeJobId);
        setIsLoadingJob(true);
        getJob(activeJobId)
          .then(setJob)
          .catch(() => setJob(null))
          .finally(() => setIsLoadingJob(false));
      }
    } else if (jobStatus === 'running' && !job?.result_data) {
      setActiveTab('logs');
    }
  }

  // Auto-switch to results when partial results arrive during execution
  if (
    jobStatus === 'running' &&
    quickStatus?.result_data &&
    Object.keys(quickStatus.result_data).length > 0 &&
    activeTab === 'logs'
  ) {
    setActiveTab('results');
  }

  // Derive log entries from progress (no accumulation needed — progress
  // object retains all nodes with their final status across updates)
  const progress = quickStatus?.progress;
  const logEntries: LogEntry[] = useMemo(() => {
    if (!progress) return [];
    const entries: LogEntry[] = [];

    for (const [nodeId, info] of Object.entries(progress)) {
      if (!info || typeof info !== 'object') continue;
      const agentInfo = info as AgentProgress;
      const st = agentInfo.status;

      if (st === 'running') {
        entries.push({ timestamp: '', nodeId, message: `${nodeId} running`, level: 'info' });
      } else if (st === 'done') {
        entries.push({ timestamp: '', nodeId, message: `${nodeId} completed`, level: 'success' });
      } else if (st === 'failed') {
        entries.push({ timestamp: '', nodeId, message: `${nodeId} failed`, level: 'error' });
      }
    }
    return entries;
  }, [progress]);

  // Load snapshots on history tab click
  const handleTabClick = useCallback(
    (tabId: TabId) => {
      setActiveTab(tabId);
      if (tabId === 'history' && workflowId) {
        listSnapshots(workflowId)
          .then(setSnapshots)
          .catch(() => {});
      }
    },
    [workflowId],
  );

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = useMemo(
    () => [
      { id: 'results', label: 'Results', icon: <BarChart3 className="w-3.5 h-3.5" /> },
      { id: 'logs', label: 'Logs', icon: <Terminal className="w-3.5 h-3.5" /> },
      { id: 'properties', label: 'Properties', icon: <Info className="w-3.5 h-3.5" /> },
      { id: 'history', label: 'History', icon: <History className="w-3.5 h-3.5" /> },
    ],
    [],
  );

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex border-b border-white/10 px-1 shrink-0">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabClick(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-brand-electric border-b-2 border-brand-electric'
                : 'text-brand-silver/50 hover:text-brand-silver'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Active job status bar */}
      {activeJobId && quickStatus && (
        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10 bg-white/[0.02]">
          <JobStatusIcon status={quickStatus.status} />
          <span className="text-xs text-brand-silver truncate">
            Job: {activeJobId.slice(0, 8)}...
          </span>
          {quickStatus.progress_percent > 0 && (
            <span className="text-xs text-brand-silver/50 ml-auto">
              {quickStatus.progress_percent}%
            </span>
          )}
        </div>
      )}

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'results' && (
          <ResultsTab job={job} quickStatus={quickStatus} isLoading={isLoadingJob} />
        )}
        {activeTab === 'logs' && <LogConsole entries={logEntries} />}
        {activeTab === 'properties' && (
          <PropertiesTab nodeData={selectedNodeData} workflowDetail={workflowDetail} />
        )}
        {activeTab === 'history' && (
          <HistoryTab snapshots={snapshots} />
        )}
      </div>
    </div>
  );
}

// ── Result timestamp helper ──

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function ResultTimestamp({ timestamp, isStale }: { timestamp: string; isStale?: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 px-3 py-1.5 mb-2 rounded-lg border text-[11px] ${
      isStale
        ? 'border-amber-400/20 bg-amber-400/5 text-amber-300/80'
        : 'border-white/5 bg-white/[0.02] text-brand-silver/50'
    }`}>
      <CalendarClock className="w-3 h-3 shrink-0" />
      <span>Generated {formatTimestamp(timestamp)}</span>
    </div>
  );
}

// ── Results Tab ──

function ResultsTab({
  job,
  quickStatus,
  isLoading,
}: {
  job: AnalysisJob | null;
  quickStatus: QuickStatus | null;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 text-brand-electric animate-spin" />
      </div>
    );
  }

  // Completed/failed job with full result data
  if (job?.result_data) {
    const ts = job.completed_at ?? job.updated_at;
    return (
      <div className="p-3">
        {ts && <ResultTimestamp timestamp={ts} />}
        <ResultDashboard
          resultData={job.result_data}
          manifestName={job.manifest_name}
        />
      </div>
    );
  }

  // Partial or restored results from quick-status
  if (
    quickStatus?.result_data &&
    typeof quickStatus.result_data === 'object' &&
    Object.keys(quickStatus.result_data).length > 0
  ) {
    return (
      <div className="p-3">
        <ResultDashboard
          resultData={quickStatus.result_data}
          manifestName={quickStatus.manifest_name}
        />
        {quickStatus.status === 'running' && (
          <div className="flex items-center gap-2 mt-3 px-2 py-1.5 text-xs text-brand-electric/60">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>More results loading...</span>
          </div>
        )}
      </div>
    );
  }

  if (quickStatus?.status === 'running') {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-brand-silver/40">
        <Loader2 className="w-8 h-8 animate-spin mb-3" />
        <p className="text-sm">Pipeline executing...</p>
        {quickStatus.current_node && (
          <p className="text-xs mt-1">Running: {quickStatus.current_node}</p>
        )}
      </div>
    );
  }

  if (quickStatus?.status === 'failed') {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-red-400/60">
        <AlertCircle className="w-8 h-8 mb-3" />
        <p className="text-sm">Execution failed</p>
        {quickStatus.error_message && (
          <p className="text-xs mt-1 px-4 text-center">{quickStatus.error_message}</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-12 text-brand-silver/30">
      <BarChart3 className="w-8 h-8 mb-3" />
      <p className="text-xs">Execute a workflow to see results</p>
    </div>
  );
}

// ── Properties Tab ──

function PropertiesTab({
  nodeData,
  workflowDetail,
}: {
  nodeData?: AgentNodeData | null;
  workflowDetail?: UserWorkflowDetail | null;
}) {
  // Show agent properties when a node is selected
  if (nodeData) {
    return (
      <div className="p-3 space-y-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-brand-silver/30 mb-1">Agent</p>
          <h3 className="text-sm font-medium text-brand-silver mb-2">
            {nodeData.label}
          </h3>
          {nodeData.description && (
            <p className="text-xs text-brand-silver/50">{nodeData.description}</p>
          )}
        </div>

        <div className="space-y-2 text-xs">
          <PropertyRow label="Agent ID" value={nodeData.agentId} />
          <PropertyRow label="Type" value={nodeData.agentType} />
          <PropertyRow label="Status" value={nodeData.status || 'idle'} />
          <PropertyRow label="Health" value={nodeData.health || 'unknown'} />
        </div>
      </div>
    );
  }

  // Show workflow properties when no node is selected
  if (workflowDetail) {
    const nodeCount = workflowDetail.manifest_data?.nodes?.length ?? 0;
    const edgeCount = workflowDetail.manifest_data?.edges?.length ?? 0;

    return (
      <div className="p-3 space-y-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-brand-silver/30 mb-1">Workflow</p>
          <h3 className="text-sm font-medium text-brand-silver mb-2">
            {workflowDetail.name}
          </h3>
          {workflowDetail.description && (
            <p className="text-xs text-brand-silver/50">{workflowDetail.description}</p>
          )}
        </div>

        <div className="space-y-2 text-xs">
          <PropertyRow label="Workflow ID" value={workflowDetail.workflow_id.slice(0, 8) + '...'} />
          <PropertyRow label="Source" value={workflowDetail.source} />
          <PropertyRow label="Agents" value={String(nodeCount)} />
          <PropertyRow label="Connections" value={String(edgeCount)} />
          <PropertyRow label="Executions" value={String(workflowDetail.execution_count)} />
          <PropertyRow label="Last Run" value={
            workflowDetail.last_executed_at
              ? new Date(workflowDetail.last_executed_at).toLocaleDateString()
              : 'Never'
          } />
          <PropertyRow label="Last Status" value={workflowDetail.last_job_status || 'None'} />
          <PropertyRow label="Created By" value={workflowDetail.created_by_email || '—'} />
          <PropertyRow label="Created" value={new Date(workflowDetail.created_at).toLocaleDateString()} />
          <PropertyRow label="Updated" value={new Date(workflowDetail.updated_at).toLocaleDateString()} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-12 text-brand-silver/30">
      <Info className="w-8 h-8 mb-3" />
      <p className="text-xs">Select a workflow or node to view properties</p>
    </div>
  );
}

function PropertyRow({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-white/5">
      <span className="text-brand-silver/40">{label}</span>
      <span className="text-brand-silver font-mono text-[11px]">{value || '—'}</span>
    </div>
  );
}

// ── History Tab ──

function HistoryTab({ snapshots }: { snapshots: WorkflowSnapshot[] }) {
  if (snapshots.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-brand-silver/30">
        <History className="w-8 h-8 mb-3" />
        <p className="text-xs">No execution history yet</p>
      </div>
    );
  }

  return (
    <div className="p-2 space-y-1">
      {snapshots.map((s) => (
        <div
          key={s.snapshot_id}
          className="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-white/5 border border-transparent"
        >
          <JobStatusIcon status={s.job_status} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-brand-silver truncate">
                {s.job_id.slice(0, 8)}...
              </span>
              <span className={`text-[9px] px-1 py-0.5 rounded ${
                s.job_status === 'completed'
                  ? 'bg-emerald-400/20 text-emerald-300'
                  : s.job_status === 'failed'
                    ? 'bg-red-400/20 text-red-300'
                    : 'bg-amber-400/20 text-amber-300'
              }`}>
                {s.job_status}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-[9px] text-brand-silver/30">
              <span>{new Date(s.created_at).toLocaleDateString()}</span>
              {s.duration_seconds != null && (
                <span>{s.duration_seconds}s</span>
              )}
              {s.chat_session_id && (
                <a
                  href={`/chat?session=${s.chat_session_id}`}
                  className="text-brand-electric/60 hover:text-brand-electric"
                >
                  View in Chat
                </a>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
