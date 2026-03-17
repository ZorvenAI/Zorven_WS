/**
 * WorkflowCanvas — React Flow canvas for viewing and editing workflows.
 *
 * Phase 2: Full editing support — drag-drop from agent catalog,
 * edge creation with cycle detection, node deletion, keyboard shortcuts.
 */

'use client';

import { useCallback, useRef, useMemo, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
  type OnNodesChange,
  type OnEdgesChange,
  applyNodeChanges,
  applyEdgeChanges,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { AgentProgress } from '@/types/orchestration';
import type { AgentCatalogEntry } from '@/types/workspace';
import AgentNode, { type AgentNodeData } from './AgentNode';
import { validateConnection } from './ConnectionValidator';
import type { WorkflowAction, WorkflowState } from '@/hooks/useWorkflowStore';

// ── Types ──

interface WorkflowCanvasProps {
  state: WorkflowState;
  dispatch: React.Dispatch<WorkflowAction>;
  progress?: Record<string, AgentProgress>;
  readonly?: boolean;
  /** Fires when a node is selected (data) or deselected (null). */
  onNodeSelect?: (data: AgentNodeData | null) => void;
}

// ── Node types ──

const nodeTypes = { agent: AgentNode };

// ── Edge styles ──

function getEdgeStyle(
  sourceId: string,
  progress: Record<string, AgentProgress>,
) {
  const status = progress[sourceId]?.status;
  return {
    stroke:
      status === 'done'
        ? '#34d399'
        : status === 'running'
          ? '#fad55c'
          : '#94a3b8',
    strokeWidth: 2,
  };
}

// ── Counter for unique node IDs ──

let nodeCounter = 0;

// ── Component ──

export default function WorkflowCanvas({
  state,
  dispatch,
  progress = {},
  readonly = false,
  onNodeSelect,
}: WorkflowCanvasProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();

  // Apply progress styling to edges
  const styledEdges = useMemo(
    () =>
      state.edges.map((e) => ({
        ...e,
        animated: progress[e.source]?.status === 'running',
        style: getEdgeStyle(e.source, progress),
      })),
    [state.edges, progress],
  );

  // Apply progress status to node data and enforce readonly draggable
  const styledNodes = useMemo(
    () =>
      state.nodes.map((n) => {
        const agentProgress = progress[n.id];
        const data = n.data as AgentNodeData;
        return {
          ...n,
          data: {
            ...data,
            ...(agentProgress ? { status: agentProgress.status } : {}),
          } as Record<string, unknown>,
          draggable: !readonly,
        };
      }),
    [state.nodes, progress, readonly],
  );

  // ── Node changes (position, selection, removal) ──

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => {
      if (readonly) return;

      // Check for removals — dispatch REMOVE_NODE for each
      const removals = changes.filter((c) => c.type === 'remove');
      if (removals.length > 0) {
        for (const r of removals) {
          if ('id' in r) {
            dispatch({ type: 'REMOVE_NODE', nodeId: r.id });
          }
        }
        return;
      }

      // Position changes — apply directly
      const updated = applyNodeChanges(changes, state.nodes);
      dispatch({ type: 'UPDATE_NODES', nodes: updated as Node[] });
    },
    [readonly, dispatch, state.nodes],
  );

  // ── Edge changes ──

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      if (readonly) return;

      const removals = changes.filter((c) => c.type === 'remove');
      if (removals.length > 0) {
        for (const r of removals) {
          if ('id' in r) {
            dispatch({ type: 'REMOVE_EDGE', edgeId: r.id });
          }
        }
        return;
      }

      const updated = applyEdgeChanges(changes, state.edges);
      dispatch({ type: 'UPDATE_EDGES', edges: updated });
    },
    [readonly, dispatch, state.edges],
  );

  // ── New connection (edge creation) with cycle detection ──

  // Use a ref for edges so the validation callback always sees the latest value
  const edgesRef = useRef(state.edges);
  edgesRef.current = state.edges;

  const onConnect = useCallback(
    (connection: Connection) => {
      if (readonly) return;

      const error = validateConnection(connection, edgesRef.current);
      if (error) return;

      const edge: Edge = {
        id: `e-${connection.source}-${connection.target}`,
        source: connection.source!,
        target: connection.target!,
        style: { stroke: '#94a3b8', strokeWidth: 2 },
      };
      dispatch({ type: 'ADD_EDGE', edge });
    },
    [readonly, dispatch],
  );

  // ── Drag-and-drop from agent catalog ──

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      if (readonly) return;
      event.preventDefault();

      const data = event.dataTransfer.getData('application/reactflow');
      if (!data) return;

      let agent: AgentCatalogEntry;
      try {
        agent = JSON.parse(data) as AgentCatalogEntry;
      } catch {
        return;
      }

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      // Check if this agent already exists (for unique agents)
      const existingIds = state.nodes.map((n) => n.id);
      let nodeId = agent.id;
      if (existingIds.includes(nodeId)) {
        nodeCounter++;
        nodeId = `${agent.id}_${nodeCounter}`;
      }

      const meta = {
        label: agent.label,
        description: agent.description,
        icon: agent.icon ?? '',
      };

      const newNode: Node = {
        id: nodeId,
        type: 'agent',
        position,
        data: {
          label: meta.label,
          agentId: agent.id,
          description: meta.description,
          agentType: agent.type,
          url: agent.url,
          handler: agent.handler,
          health: agent.health,
          status: 'pending',
          icon: meta.icon,
        } as Record<string, unknown>,
        draggable: true,
      };

      dispatch({ type: 'ADD_NODE', node: newNode as Node });
    },
    [readonly, screenToFlowPosition, state.nodes, dispatch],
  );

  // ── Listen for agent-delete events from AgentNode buttons ──

  useEffect(() => {
    if (readonly) return;

    function handleAgentDelete(e: Event) {
      const nodeId = (e as CustomEvent).detail?.nodeId;
      if (nodeId) {
        dispatch({ type: 'REMOVE_NODE', nodeId });
      }
    }

    window.addEventListener('agent-delete', handleAgentDelete);
    return () => window.removeEventListener('agent-delete', handleAgentDelete);
  }, [readonly, dispatch]);

  // ── Viewport change ──

  const onMoveEnd = useCallback(
    (_event: unknown, viewport: { x: number; y: number; zoom: number }) => {
      dispatch({ type: 'SET_VIEWPORT', viewport });
    },
    [dispatch],
  );

  // ── Node selection → notify parent ──

  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }: { nodes: Node[] }) => {
      if (!onNodeSelect) return;
      if (selectedNodes.length === 1) {
        onNodeSelect(selectedNodes[0].data as AgentNodeData);
      } else {
        onNodeSelect(null);
      }
    },
    [onNodeSelect],
  );

  // ── Read-only empty state (no workflow selected) ──

  if (state.nodes.length === 0 && readonly) {
    return (
      <div className="flex items-center justify-center h-full text-brand-silver/50">
        <p>Select a workflow to view its pipeline graph</p>
      </div>
    );
  }

  // ── Single ReactFlow instance for both empty and populated states ──
  // Using one instance avoids remounting which loses internal connection state.

  return (
    <div ref={reactFlowWrapper} className="w-full h-full" onDragOver={onDragOver} onDrop={onDrop}>
      <ReactFlow
        nodes={styledNodes}
        edges={styledEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onMoveEnd={onMoveEnd}
        onSelectionChange={onSelectionChange}
        nodesConnectable={!readonly}
        connectionRadius={40}
        connectionLineStyle={{ stroke: '#fad55c', strokeWidth: 2 }}
        fitView
        fitViewOptions={{ padding: 0.3, maxZoom: 1 }}
        deleteKeyCode={readonly ? null : ['Backspace', 'Delete']}
        panOnDrag={true}
        zoomOnScroll={true}
        zoomOnPinch={true}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
        maxZoom={2}
        style={{ width: '100%', height: '100%' }}
      >
        <Background color="rgba(225, 225, 230, 0.05)" gap={20} />
        <Controls
          showInteractive={false}
          className="!bg-brand-surface !border-white/10 !rounded-lg [&>button]:!bg-brand-surface [&>button]:!border-white/10 [&>button]:!text-brand-silver"
        />
        <MiniMap
          className="!bg-brand-surface !border-white/10 !rounded-lg"
          nodeColor={() => 'rgba(250, 213, 92, 0.3)'}
          maskColor="rgba(30, 30, 46, 0.8)"
        />

        {/* Empty state overlay */}
        {state.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
            <div className="text-center text-brand-silver/30">
              <p className="text-sm mb-1">Drop agents here to start building</p>
              <p className="text-xs">or select a workflow from the sidebar</p>
            </div>
          </div>
        )}
      </ReactFlow>
    </div>
  );
}
