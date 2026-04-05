/**
 * Workflow Management Workspace page.
 *
 * Phase 3: Full editing + real-time execution monitoring via WebSocket,
 * results inspector, live canvas animation.
 */

'use client';

import { useState, useEffect, useCallback, useRef, useMemo, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { ReactFlowProvider, useReactFlow } from '@xyflow/react';
import { useAuth } from '@/hooks/useAuth';
import { useTenantContext } from '@/contexts/TenantContext';
import { useBrandContext } from '@/hooks/useBrandContext';
import {
  listWorkflows,
  getWorkflow,
  patchWorkflow,
  updateWorkflow,
  createWorkflow,
  deleteWorkflow,
  executeWorkflow,
  exportWorkflow,
  importWorkflow,
  acquireLock,
  releaseLock,
  getLockInfo,
  listTemplates,
} from '@/lib/workspace';
import { computeElkLayout } from '@/lib/elkLayout';
import { useWorkflowStore, restoreDraft } from '@/hooks/useWorkflowStore';
import { useWorkspaceWebSocket, type WorkspaceWSEvent } from '@/hooks/useWorkspaceWebSocket';
import { usePollingJob } from '@/hooks/usePollingJob';
import type {
  UserWorkflowSummary,
  UserWorkflowDetail,
  LockInfo,
} from '@/types/workspace';
import type {
  AgentProgress,
  ManifestGraphData,
  PipelineManifest,
  QuickStatus,
} from '@/types/orchestration';
import type { Node, Edge } from '@xyflow/react';
import WorkspaceLayout from '@/components/workspace/WorkspaceLayout';
import WorkflowSidebar from '@/components/workspace/WorkflowSidebar';
import WorkflowCanvas from '@/components/workspace/WorkflowCanvas';
import WorkflowToolbar from '@/components/workspace/WorkflowToolbar';
import ResultsInspector from '@/components/workspace/ResultsInspector';
import AgentInfoModal from '@/components/workspace/AgentInfoModal';
import WorkflowInfoModal from '@/components/workspace/WorkflowInfoModal';
import { listAgents } from '@/lib/workspace';
import type { AgentCatalogEntry } from '@/types/workspace';
import type { AgentNodeData } from '@/components/workspace/AgentNode';

// ── Agent metadata for enriching loaded nodes ──

const AGENT_META: Record<string, { label: string; description: string; icon: string }> = {
  discovery: { label: 'Web Discovery', description: 'Web research via Tavily', icon: 'search' },
  market_research: { label: 'Market Research', description: 'Market sizing, TAM/SAM/SOM', icon: 'bar-chart-3' },
  competitor_intelligence: { label: 'Competitor Intel', description: 'Competitor profiling, SWOT', icon: 'swords' },
  audience_persona: { label: 'Audience Persona', description: 'Buyer persona profiling', icon: 'user-search' },
  trend_cultural: { label: 'Trend & Cultural', description: 'Trend monitoring & insights', icon: 'trending-up' },
  voice_of_customer: { label: 'Voice of Customer', description: 'VoC analysis, NPS', icon: 'message-circle' },
  intelligence: { label: 'Brand Valuation', description: 'ISO 10668 brand equity', icon: 'gem' },
  content: { label: 'Content Author', description: 'SEO/AEO/GEO blog authoring', icon: 'pen-tool' },
  social: { label: 'Social Promoter', description: 'Social media publishing', icon: 'share-2' },
  rag_uploader: { label: 'RAG Uploader', description: 'Archive to Vertex AI RAG', icon: 'database' },
  odoo_worker: { label: 'Odoo Worker', description: 'ERP operations via Odoo', icon: 'briefcase' },
  router: { label: 'Intent Router', description: 'Routes to correct pipeline', icon: 'route' },
  manager: { label: 'Pipeline Manager', description: 'Aggregates agent outputs', icon: 'layout-dashboard' },
  strategy: { label: 'Brand Strategy', description: 'Strategy analysis', icon: 'target' },
  report: { label: 'Report Generator', description: 'Executive summary reports', icon: 'file-text' },
  audience: { label: 'Audience Analysis', description: 'Demographics & segmentation', icon: 'users' },
  planner: { label: 'Content Planner', description: 'Content planning', icon: 'calendar' },
  calendar: { label: 'Editorial Calendar', description: 'Calendar schedules', icon: 'calendar-days' },
};

function humanLabel(nodeId: string): string {
  return nodeId.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Convert ManifestGraphData + LayoutData into React Flow nodes/edges. */
function manifestToFlow(
  manifest: ManifestGraphData,
  layoutNodes?: Record<string, { x: number; y: number }>,
): { nodes: Node[]; edges: Edge[] } {
  const nodes = manifest.nodes.map((n, idx) => {
    const meta = AGENT_META[n.id] ?? {
      label: n.label ?? humanLabel(n.id),
      description: '',
      icon: '',
    };
    const pos = layoutNodes?.[n.id] ?? { x: idx * 260, y: 40 };
    return {
      id: n.id,
      type: 'agent' as const,
      position: pos,
      data: {
        label: meta.label,
        agentId: n.id,
        description: meta.description,
        agentType: n.type,
        url: n.url,
        handler: n.handler,
        health: 'unknown' as const,
        status: 'pending' as const,
        icon: meta.icon,
      },
      draggable: true,
    };
  }) satisfies Node[];

  const edges: Edge[] = manifest.edges.map(([src, dst]) => ({
    id: `e-${src}-${dst}`,
    source: src,
    target: dst,
    style: { stroke: '#94a3b8', strokeWidth: 2 },
  }));

  return { nodes, edges };
}

// ── Inner component (needs ReactFlowProvider) ──

function WorkflowsPageInner() {
  const [hasMounted, setHasMounted] = useState(false);
  const [workflows, setWorkflows] = useState<UserWorkflowSummary[]>([]);
  const [templates, setTemplates] = useState<PipelineManifest[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem('workspace-selected-workflow');
    } catch {
      return null;
    }
  });
  const [selectedDetail, setSelectedDetail] = useState<UserWorkflowDetail | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [selectedTemplateName, setSelectedTemplateName] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lockInfo, setLockInfo] = useState<LockInfo | null>(null);
  const lockHeartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const lockInfoRef = useRef<LockInfo | null>(null);

  // Execution tracking
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [wsProgress, setWsProgress] = useState<Record<string, AgentProgress>>({});
  const [wsQuickStatus, setWsQuickStatus] = useState<QuickStatus | null>(null);

  // Canvas selection state (for Properties tab) — store ID, derive data
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Modal state
  const [agentInfoTarget, setAgentInfoTarget] = useState<AgentNodeData | AgentCatalogEntry | null>(null);
  const [showWorkflowInfo, setShowWorkflowInfo] = useState(false);
  const [agentCatalog, setAgentCatalog] = useState<AgentCatalogEntry[]>([]);

  const { zoomIn, zoomOut } = useReactFlow();
  const { activeTenant } = useTenantContext();
  const { activeBrand } = useBrandContext();
  const searchParams = useSearchParams();
  const store = useWorkflowStore(selectedId);

  const isTemplatePreview = selectedTemplateId !== null;
  const isReadonly = isTemplatePreview || (lockInfo?.locked === true && !lockInfo?.is_mine);

  // Keep refs in sync for cleanup on unmount (avoids stale closure)
  selectedIdRef.current = selectedId;
  lockInfoRef.current = lockInfo;

  // Derive current node data from store (always fresh with latest progress)
  const selectedNodeData = useMemo(() => {
    if (!selectedNodeId) return null;
    const node = store.state.nodes.find((n) => n.id === selectedNodeId);
    return node ? (node.data as AgentNodeData) : null;
  }, [selectedNodeId, store.state.nodes]);

  // ── WebSocket for real-time updates ──

  const handleWSEvent = useCallback((event: WorkspaceWSEvent) => {
    const { data } = event;

    // Only process events for the active job
    if (activeJobId && data.job_id !== activeJobId) return;

    // Update progress for canvas animation
    setWsProgress(data.progress || {});

    // Build QuickStatus from WS event
    setWsQuickStatus({
      status: data.status,
      progress: data.progress || {},
      current_node: data.current_node,
      progress_percent: data.progress_percent,
      last_thought: null,
      error_message: data.error_message,
    });

    // On terminal state, refresh workflow list to update status badges
    if (data.status === 'completed' || data.status === 'failed') {
      listWorkflows().then(setWorkflows).catch(() => {});
    }
  }, [activeJobId]);

  useWorkspaceWebSocket({
    tenantId: activeTenant?.id ?? null,
    onEvent: handleWSEvent,
    enabled: !!activeJobId,
  });

  // ── Polling — always active when there's an active job ──
  // WebSocket may connect but not deliver events reliably, so polling
  // is the guaranteed fallback. WS events update state directly via
  // handleWSEvent and will naturally be more recent than polled data.

  const { quickStatus: pollingStatus, refresh: refreshJob } = usePollingJob(
    activeJobId,
    { intervalMs: 3000 },
  );

  // Merge: use WS data if it has arrived, otherwise fall back to polling.
  // WS events set wsQuickStatus directly; polling sets pollingStatus.
  const effectiveQuickStatus = wsQuickStatus ?? pollingStatus;

  // Update canvas progress from effective status
  useEffect(() => {
    if (effectiveQuickStatus?.progress) {
      setWsProgress(effectiveQuickStatus.progress);
    }
  }, [effectiveQuickStatus]);

  // Sync effective job status into sidebar badge so it updates in real-time
  // (covers both WebSocket and polling paths)
  useEffect(() => {
    if (!selectedId || !effectiveQuickStatus?.status) return;
    setWorkflows((prev) =>
      prev.map((w) =>
        w.workflow_id === selectedId
          ? { ...w, last_job_status: effectiveQuickStatus.status }
          : w,
      ),
    );
  }, [selectedId, effectiveQuickStatus?.status]);

  // Clear job tracking on terminal state
  useEffect(() => {
    if (
      effectiveQuickStatus?.status === 'completed' ||
      effectiveQuickStatus?.status === 'failed'
    ) {
      // Keep activeJobId so ResultsInspector can show results
      // Clear progress animation
      const timeoutId = setTimeout(() => {
        setWsProgress({});
      }, 2000);
      return () => clearTimeout(timeoutId);
    }
  }, [effectiveQuickStatus?.status]);

  // Persist selectedId to sessionStorage for cross-navigation continuity
  useEffect(() => {
    try {
      if (selectedId) {
        sessionStorage.setItem('workspace-selected-workflow', selectedId);
      } else {
        sessionStorage.removeItem('workspace-selected-workflow');
      }
    } catch {
      // sessionStorage unavailable
    }
  }, [selectedId]);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  // ── Listen for agent-info custom events (from AgentNode / AgentCatalogPanel) ──

  useEffect(() => {
    function handleAgentInfo(e: Event) {
      const detail = (e as CustomEvent).detail;
      if (detail) setAgentInfoTarget(detail);
    }
    window.addEventListener('agent-info', handleAgentInfo);
    return () => window.removeEventListener('agent-info', handleAgentInfo);
  }, []);

  // ── Fetch agent catalog (for WorkflowInfoModal) ──

  useEffect(() => {
    if (!hasMounted) return;
    listAgents().then(setAgentCatalog).catch(() => {});
  }, [hasMounted]);

  // ── Fetch workflow list and templates ──

  useEffect(() => {
    if (!hasMounted) return;
    let cancelled = false;

    async function fetchData() {
      try {
        setIsLoading(true);
        const [wfData, tmplData] = await Promise.all([
          listWorkflows(),
          listTemplates().catch(() => []),
        ]);
        if (!cancelled) {
          setWorkflows(wfData);
          setTemplates(tmplData);
          setError(null);
          // Clear stale selectedId if it no longer exists in the list
          // (e.g. new brand with no workflows, or workflow was deleted)
          setSelectedId((prev) => {
            if (prev && wfData.length > 0 && !wfData.some((w) => w.workflow_id === prev)) {
              return null;
            }
            if (prev && wfData.length === 0) {
              return null;
            }
            return prev;
          });
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load workflows');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    fetchData();
    return () => { cancelled = true; };
  }, [hasMounted]);

  // ── Auto-select workflow from ?workflow= query param ──

  useEffect(() => {
    const workflowParam = searchParams.get('workflow');
    if (workflowParam && workflows.length > 0 && !selectedId) {
      const match = workflows.find((w) => w.workflow_id === workflowParam);
      if (match) {
        setSelectedId(match.workflow_id);
      }
    }
  }, [searchParams, workflows, selectedId]);

  // ── Fetch selected workflow detail ──

  useEffect(() => {
    if (!selectedId) {
      setSelectedDetail(null);
      setLockInfo(null);
      return;
    }
    let cancelled = false;

    async function fetchDetail() {
      try {
        setIsDetailLoading(true);
        const [detail, lock] = await Promise.all([
          getWorkflow(selectedId!),
          getLockInfo(selectedId!).catch(() => ({ locked: false }) as LockInfo),
        ]);
        if (!cancelled) {
          setSelectedDetail(detail);
          setLockInfo(lock);

          // Restore active job from last execution so results
          // persist across page refreshes / workflow re-selection.
          // Sets null for never-executed workflows (clears stale state).
          setActiveJobId(detail.last_job_id);
          setWsQuickStatus(null);

          // Load into store — check for unsaved draft first
          if (detail.manifest_data) {
            const draft = restoreDraft(selectedId!);
            const apiUpdatedAt = detail.updated_at
              ? new Date(detail.updated_at).getTime()
              : 0;

            if (draft && draft.savedAt > apiUpdatedAt) {
              // Draft is newer than the last save — restore unsaved edits
              const draftNodes: Node[] = draft.nodes.map((n) => ({
                id: n.id,
                type: (n.type as string) ?? 'agent',
                position: n.position,
                data: n.data as Record<string, unknown>,
                draggable: true,
              }));
              const draftEdges: Edge[] = draft.edges.map((e) => ({
                id: e.id,
                source: e.source,
                target: e.target,
                style: { stroke: '#94a3b8', strokeWidth: 2 },
              }));
              store.dispatch({ type: 'LOAD_DIRTY', nodes: draftNodes, edges: draftEdges });
            } else {
              // No draft or draft is stale — load from API
              const { nodes, edges } = manifestToFlow(
                detail.manifest_data,
                detail.layout_data?.nodes,
              );
              store.dispatch({ type: 'LOAD', nodes, edges });
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Failed to load workflow detail:', err);
          setSelectedDetail(null);
          // Clear stale selection on 404 (e.g. workflow deleted or new brand)
          if (err instanceof Error && err.message.includes('404')) {
            setSelectedId(null);
          }
        }
      } finally {
        if (!cancelled) setIsDetailLoading(false);
      }
    }

    fetchDetail();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // ── Lock heartbeat (refresh every 5 min) ──

  useEffect(() => {
    if (lockHeartbeatRef.current) {
      clearInterval(lockHeartbeatRef.current);
      lockHeartbeatRef.current = null;
    }

    if (selectedId && lockInfo?.is_mine) {
      lockHeartbeatRef.current = setInterval(async () => {
        try {
          await acquireLock(selectedId);
        } catch {
          // ignore
        }
      }, 5 * 60 * 1000);
    }

    return () => {
      if (lockHeartbeatRef.current) {
        clearInterval(lockHeartbeatRef.current);
      }
    };
  }, [selectedId, lockInfo?.is_mine]);

  // ── Actions ──

  const handleSelect = useCallback((workflowId: string) => {
    // Always attempt lock release on previous workflow — even if lockInfo
    // hasn't resolved yet. releaseLock tolerates 403 (not holder) gracefully.
    if (selectedId) {
      releaseLock(selectedId).catch(() => {});
    }
    setSelectedId(workflowId);
    setLockInfo(null);
    // Clear template preview when selecting a workflow
    setSelectedTemplateId(null);
    setSelectedTemplateName(null);
    // Clear job tracking and node selection when switching workflows
    setActiveJobId(null);
    setWsProgress({});
    setWsQuickStatus(null);
    setSelectedNodeId(null);
  }, [selectedId]);

  const handleSelectTemplate = useCallback((templateId: string) => {
    // Find template in the list (typed as PipelineManifest with manifest_data)
    const tmpl = templates.find((t) => String(t.id) === templateId);
    if (!tmpl || !tmpl.manifest_data) {
      setError(tmpl ? 'Template has no graph data to preview' : 'Template not found');
      return;
    }

    // Clear workflow selection — always attempt lock release
    if (selectedId) {
      releaseLock(selectedId).catch(() => {});
    }
    setSelectedId(null);
    setSelectedDetail(null);
    setLockInfo(null);
    setActiveJobId(null);
    setWsProgress({});
    setWsQuickStatus(null);
    setSelectedNodeId(null);

    // Set template preview state
    setSelectedTemplateId(templateId);
    setSelectedTemplateName(tmpl.name);

    // Load template graph into canvas
    const { nodes, edges } = manifestToFlow(
      tmpl.manifest_data as unknown as ManifestGraphData,
    );
    store.dispatch({ type: 'LOAD', nodes, edges });
  }, [templates, selectedId, store]);

  const handleCreateNew = useCallback(async () => {
    const name = window.prompt('Workflow name:', `Untitled Workflow ${workflows.length + 1}`);
    if (!name?.trim()) return;

    try {
      const workflow = await createWorkflow({
        name: name.trim(),
        manifest_data: {
          nodes: [{ id: 'manager', type: 'internal', handler: 'ManagerNode' }],
          edges: [],
        },
        layout_data: { nodes: { manager: { x: 300, y: 200 } }, viewport: { x: 0, y: 0, zoom: 1 } },
      });
      setWorkflows((prev) => [
        {
          ...workflow,
          last_job_status: null,
        } as UserWorkflowSummary,
        ...prev,
      ]);
      setSelectedId(workflow.workflow_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workflow');
    }
  }, [workflows.length]);

  const handleToggleFavorite = useCallback(async (workflowId: string, isFavorite: boolean) => {
    try {
      await patchWorkflow(workflowId, { is_favorite: isFavorite });
      setWorkflows((prev) =>
        prev.map((w) =>
          w.workflow_id === workflowId ? { ...w, is_favorite: isFavorite } : w,
        ),
      );
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
    }
  }, []);

  const handleDelete = useCallback(async (workflowId: string) => {
    try {
      await deleteWorkflow(workflowId);
      setWorkflows((prev) => prev.filter((w) => w.workflow_id !== workflowId));
      if (selectedId === workflowId) {
        setSelectedId(null);
        setSelectedDetail(null);
        setLockInfo(null);
        setActiveJobId(null);
        store.dispatch({ type: 'LOAD', nodes: [], edges: [] });
        try { sessionStorage.removeItem('workspace-selected-workflow'); } catch { /* ignore */ }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete workflow');
    }
  }, [selectedId, store]);

  const handleRename = useCallback(async (workflowId: string, newName: string) => {
    try {
      await patchWorkflow(workflowId, { name: newName });
      setWorkflows((prev) =>
        prev.map((w) =>
          w.workflow_id === workflowId ? { ...w, name: newName } : w,
        ),
      );
      if (selectedDetail?.workflow_id === workflowId) {
        setSelectedDetail((prev) => prev ? { ...prev, name: newName } : prev);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename workflow');
    }
  }, [selectedDetail?.workflow_id]);

  const handleShowWorkflowInfo = useCallback((workflowId: string) => {
    // If the workflow is already selected and detail loaded, just show the modal.
    // Otherwise, select it first — the detail fetch effect will load it.
    if (workflowId === selectedId && selectedDetail) {
      setShowWorkflowInfo(true);
    } else {
      // Select the workflow (detail will load), then show modal after detail arrives
      setSelectedId(workflowId);
      // We'll show the modal once detail is loaded — set a flag
      setShowWorkflowInfo(true);
    }
  }, [selectedId, selectedDetail]);

  const handleCloneTemplate = useCallback(async (templateId: string, templateName: string) => {
    try {
      // Re-fetch templates to get the latest manifest_data (avoids stale browser state)
      const freshTemplates = await listTemplates();
      const templateManifest = freshTemplates.find((t) => String(t.id) === templateId);
      if (!templateManifest || !templateManifest.manifest_data) return;

      // Create a new workflow using the template name
      const workflow = await createWorkflow({
        name: `${templateName} (copy)`,
        description: `Created from template: ${templateName}`,
        manifest_data: templateManifest.manifest_data as unknown as ManifestGraphData,
      });
      setWorkflows((prev) => [
        { ...workflow, last_job_status: null } as UserWorkflowSummary,
        ...prev,
      ]);
      setSelectedId(workflow.workflow_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create from template');
    }
  }, []);

  const handleSave = useCallback(async () => {
    if (!selectedId || !selectedDetail || isReadonly) return;

    try {
      setIsSaving(true);

      // Acquire lock if not held
      if (!lockInfo?.is_mine) {
        const result = await acquireLock(selectedId);
        if (result.status === 'locked') {
          setError(`Workflow is locked by ${result.locked_by}`);
          return;
        }
        setLockInfo({ locked: true, is_mine: true, locked_by: result.locked_by });
      }

      const manifestData = store.toManifestData();
      const layoutData = store.toLayoutData();

      await updateWorkflow(selectedId, {
        manifest_data: manifestData,
        layout_data: layoutData,
      });

      store.markSaved();
      store.clearDraft();
      setError(null);

      // Update list
      setWorkflows((prev) =>
        prev.map((w) =>
          w.workflow_id === selectedId
            ? { ...w, updated_at: new Date().toISOString() }
            : w,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setIsSaving(false);
    }
  }, [selectedId, selectedDetail, isReadonly, lockInfo?.is_mine, store]);

  const handleExecute = useCallback(async () => {
    if (!selectedId || isReadonly) return;

    const prompt = window.prompt('Enter analysis prompt:');
    if (!prompt?.trim()) return;

    try {
      // Save first if dirty
      if (store.state.isDirty) {
        await handleSave();
      }

      // Inject brand context into execution payload
      const inputContext: Record<string, unknown> = {
        brand_context_id: activeBrand?.brand_context_id || 'parent',
        brand_scope: activeBrand?.brand_scope || 'parent',
      };
      if (activeBrand?.parent_brand) {
        inputContext.parent_brand = activeBrand.parent_brand;
      }
      if (activeBrand?.name && activeBrand.brand_scope !== 'parent') {
        inputContext.company_name = activeBrand.name;
      }

      const job = await executeWorkflow(selectedId, {
        input_prompt: prompt.trim(),
        input_context: inputContext,
      });
      setError(null);

      // Track the active job for WebSocket/polling
      setActiveJobId(job.job_id);
      setWsProgress({});
      setWsQuickStatus(null);

      // Refresh list to show running status
      const data = await listWorkflows();
      setWorkflows(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute');
    }
  }, [selectedId, isReadonly, store.state.isDirty, handleSave, activeBrand]);

  const handleAutoLayout = useCallback(async () => {
    if (store.state.nodes.length === 0) return;

    try {
      const { nodes } = await computeElkLayout(
        store.state.nodes,
        store.state.edges,
      );
      store.dispatch({ type: 'UPDATE_NODES', nodes });
    } catch (err) {
      console.error('Auto-layout failed:', err);
    }
  }, [store]);

  const handleExport = useCallback(async () => {
    if (!selectedId) return;

    try {
      const data = await exportWorkflow(selectedId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${data.name.replace(/\s+/g, '_')}.workflow.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export');
    }
  }, [selectedId]);

  const handleImport = useCallback(async () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const workflow = await importWorkflow({
          name: data.name ?? file.name.replace('.workflow.json', ''),
          description: data.description ?? '',
          manifest_data: data.manifest_data,
          layout_data: data.layout_data,
        });
        setWorkflows((prev) => [
          { ...workflow, last_job_status: null } as UserWorkflowSummary,
          ...prev,
        ]);
        setSelectedId(workflow.workflow_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to import');
      }
    };
    input.click();
  }, []);

  // ── Keyboard shortcuts ──

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Ctrl+S / Cmd+S → Save
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
        return;
      }

      // Ctrl+Z → Undo
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        store.undo();
        return;
      }

      // Ctrl+Shift+Z → Redo
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && e.shiftKey) {
        e.preventDefault();
        store.redo();
        return;
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSave, store]);

  // ── Cleanup lock on unmount ──

  useEffect(() => {
    return () => {
      if (selectedIdRef.current && lockInfoRef.current?.is_mine) {
        releaseLock(selectedIdRef.current).catch(() => {});
      }
    };
  }, [releaseLock]);

  if (!hasMounted) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="w-8 h-8 border-2 border-brand-electric border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-64px)]">
      <WorkspaceLayout
        forceRightOpen={
          effectiveQuickStatus?.status === 'completed' ||
          effectiveQuickStatus?.status === 'failed' ||
          effectiveQuickStatus?.status === 'awaiting_approval'
        }
        leftPanel={
          <WorkflowSidebar
            workflows={workflows}
            selectedId={selectedId}
            onSelect={handleSelect}
            onCreateNew={handleCreateNew}
            onToggleFavorite={handleToggleFavorite}
            onDelete={handleDelete}
            onRename={handleRename}
            onShowInfo={handleShowWorkflowInfo}
            onCloneTemplate={handleCloneTemplate}
            onSelectTemplate={handleSelectTemplate}
            selectedTemplateId={selectedTemplateId}
            templates={templates}
            isLoading={isLoading}
          />
        }
        toolbar={
          selectedDetail ? (
            <WorkflowToolbar
              onSave={handleSave}
              onExecute={handleExecute}
              onAutoLayout={handleAutoLayout}
              onUndo={store.undo}
              onRedo={store.redo}
              onZoomIn={() => zoomIn()}
              onZoomOut={() => zoomOut()}
              onExport={handleExport}
              onImport={handleImport}
              canUndo={store.canUndo}
              canRedo={store.canRedo}
              isDirty={store.state.isDirty}
              isSaving={isSaving}
              isReadonly={isReadonly}
              lockHolder={
                lockInfo?.locked && !lockInfo?.is_mine
                  ? lockInfo?.locked_by ?? 'another user'
                  : null
              }
            />
          ) : undefined
        }
        centerPanel={
          <div className="h-full relative">
            {error && (
              <div className="absolute inset-x-0 top-0 z-10 mx-4 mt-4">
                <div className="glass-card border border-red-500/30 p-3 flex items-center justify-between">
                  <p className="text-sm text-red-300">{error}</p>
                  <button
                    onClick={() => setError(null)}
                    className="text-red-300/50 hover:text-red-300 text-xs ml-2"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}

            {isReadonly && !isTemplatePreview && (
              <div className="absolute inset-x-0 top-0 z-10 mx-4 mt-4">
                <div className="glass-card border border-amber-400/30 p-2 text-center">
                  <p className="text-xs text-amber-300">
                    Read-only: locked by {lockInfo?.locked_by ?? 'another user'}
                  </p>
                </div>
              </div>
            )}

            {isDetailLoading ? (
              <div className="flex items-center justify-center h-full">
                <div className="w-6 h-6 border-2 border-brand-electric border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (
              <WorkflowCanvas
                state={store.state}
                dispatch={store.dispatch}
                progress={wsProgress}
                readonly={isReadonly}
                onNodeSelect={setSelectedNodeId}
              />
            )}

            {/* Workflow / template title overlay */}
            {(selectedDetail || isTemplatePreview) && (
              <div className="absolute top-3 left-3 z-10">
                <div className="glass-card px-3 py-1.5">
                  <h2 className="text-sm font-heading font-semibold text-white">
                    {isTemplatePreview ? selectedTemplateName : selectedDetail?.name}
                  </h2>
                  {isTemplatePreview ? (
                    <p className="text-[10px] text-brand-electric/60 mt-0.5">
                      Template preview — Clone to edit
                    </p>
                  ) : selectedDetail?.description ? (
                    <p className="text-[10px] text-brand-silver/50 mt-0.5 max-w-[300px] truncate">
                      {selectedDetail.description}
                    </p>
                  ) : null}
                </div>
              </div>
            )}
          </div>
        }
        rightPanel={
          selectedId ? (
            <ResultsInspector
              workflowId={selectedId}
              activeJobId={activeJobId}
              quickStatus={effectiveQuickStatus ?? null}
              selectedNodeData={selectedNodeData}
              workflowDetail={selectedDetail}
              onApprovalComplete={refreshJob}
            />
          ) : undefined
        }
      />

      {/* Agent info modal */}
      {agentInfoTarget && (
        <AgentInfoModal
          agent={agentInfoTarget}
          onClose={() => setAgentInfoTarget(null)}
        />
      )}

      {/* Workflow info modal */}
      {showWorkflowInfo && selectedDetail && (
        <WorkflowInfoModal
          workflow={selectedDetail}
          agents={agentCatalog}
          onClose={() => setShowWorkflowInfo(false)}
        />
      )}
    </div>
  );
}

// ── Exported page (wraps with ReactFlowProvider) ──

export default function WorkflowsPage() {
  useAuth();

  return (
    <Suspense fallback={null}>
      <ReactFlowProvider>
        <WorkflowsPageInner />
      </ReactFlowProvider>
    </Suspense>
  );
}
