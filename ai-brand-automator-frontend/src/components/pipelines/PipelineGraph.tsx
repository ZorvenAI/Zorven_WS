/**
 * PipelineGraph — React Flow DAG visualization of a pipeline manifest.
 *
 * Renders the manifest's nodes and edges as a left-to-right graph.
 * Each node is color-coded by its execution status (pending, running,
 * done, failed) and shows the humanized label + status text.
 *
 * Used in the [jobId] detail page when manifest_data is available,
 * replacing the linear ThoughtTrace stepper with a topology view.
 */

'use client';

import { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  type Node,
  type Edge,
  Position,
  Handle,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
} from 'lucide-react';
import type {
  AgentProgress,
  ManifestGraphData,
} from '@/types/orchestration';

// ── Types ──

interface PipelineGraphProps {
  manifestData: ManifestGraphData;
  progress: Record<string, AgentProgress>;
}

type NodeStatus = AgentProgress['status'];

interface PipelineNodeData {
  label: string;
  status: NodeStatus;
  output?: Record<string, unknown>;
  [key: string]: unknown;
}

// ── Helpers ──

function humanLabel(nodeId: string): string {
  return nodeId
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Topological sort for left-to-right layout positioning.
 * Returns nodes in dependency order.
 */
function topologicalOrder(
  nodes: ManifestGraphData['nodes'],
  edges: ManifestGraphData['edges'],
): string[] {
  const adj = new Map<string, string[]>();
  const inDeg = new Map<string, number>();

  for (const n of nodes) {
    adj.set(n.id, []);
    inDeg.set(n.id, 0);
  }
  for (const [src, dst] of edges) {
    adj.get(src)?.push(dst);
    inDeg.set(dst, (inDeg.get(dst) ?? 0) + 1);
  }

  const queue: string[] = [];
  for (const [id, deg] of inDeg) {
    if (deg === 0) queue.push(id);
  }

  const order: string[] = [];
  while (queue.length > 0) {
    const node = queue.shift()!;
    order.push(node);
    for (const neighbor of adj.get(node) ?? []) {
      const d = (inDeg.get(neighbor) ?? 1) - 1;
      inDeg.set(neighbor, d);
      if (d === 0) queue.push(neighbor);
    }
  }

  // Include any remaining nodes (isolated or cyclic fallback).
  // If any nodes remain here, we likely have a cycle or malformed manifest.
  const remaining = nodes.filter((n) => !order.includes(n.id));
  if (remaining.length > 0) {
    // Backend should already validate manifests as acyclic; reaching this
    // branch indicates a potential bug or data inconsistency.
    console.warn(
      '[PipelineGraph] Detected cyclic or unresolvable nodes in manifest:',
      remaining.map((n) => n.id),
    );
    for (const n of remaining) {
      order.push(n.id);
    }
  }

  return order;
}

// ── Status styling ──

const STATUS_BORDER: Record<NodeStatus, string> = {
  pending: 'border-brand-silver/30',
  running: 'border-brand-electric animate-pulse',
  done: 'border-emerald-400',
  failed: 'border-red-400',
};

const STATUS_ICON: Record<NodeStatus, React.ReactNode> = {
  pending: <Circle className="w-4 h-4 text-brand-silver/40" />,
  running: <Loader2 className="w-4 h-4 text-brand-electric animate-spin" />,
  done: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
  failed: <XCircle className="w-4 h-4 text-red-400" />,
};

const STATUS_LABEL: Record<NodeStatus, string> = {
  pending: 'Waiting',
  running: 'Running\u2026',
  done: 'Done',
  failed: 'Failed',
};

// ── Custom Node Component ──

function PipelineNode({ data }: { data: PipelineNodeData }) {
  const status = data.status;

  return (
    <div
      className={`
        relative rounded-xl border-2 bg-white/5 backdrop-blur-sm
        px-4 py-3 min-w-[140px] transition-all duration-300
        ${STATUS_BORDER[status]}
      `}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-brand-silver/30 !w-2 !h-2 !border-0"
      />

      <div className="flex items-center gap-2">
        {STATUS_ICON[status]}
        <span className="text-sm font-medium text-brand-silver truncate">
          {data.label}
        </span>
      </div>

      <p className="mt-1 text-[11px] text-brand-silver/50">
        {STATUS_LABEL[status]}
      </p>

      <Handle
        type="source"
        position={Position.Right}
        className="!bg-brand-silver/30 !w-2 !h-2 !border-0"
      />
    </div>
  );
}

const nodeTypes = { pipeline: PipelineNode };

// ── Main Component ──

export default function PipelineGraph({
  manifestData,
  progress,
}: PipelineGraphProps) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const order = topologicalOrder(manifestData.nodes, manifestData.edges);

    const rfNodes: Node<PipelineNodeData>[] = order.map((id, idx) => {
      const agent = progress[id] ?? { status: 'pending' as const };
      return {
        id,
        type: 'pipeline',
        position: { x: idx * 220, y: 0 },
        data: {
          label: humanLabel(id),
          status: agent.status,
          output: agent.output,
        },
        draggable: false,
      };
    });

    const rfEdges: Edge[] = manifestData.edges.map(([src, dst], idx) => ({
      id: `e-${idx}`,
      source: src,
      target: dst,
      animated: progress[src]?.status === 'running',
      style: {
        stroke:
          progress[src]?.status === 'done'
            ? '#34d399'
            : 'rgba(225, 225, 230, 0.2)',
        strokeWidth: 2,
      },
    }));

    return { rfNodes, rfEdges };
  }, [manifestData, progress]);

  return (
    <div className="glass-card p-4">
      <h3 className="text-sm font-heading font-semibold text-white mb-3">
        Pipeline Topology
      </h3>
      <div
        className="rounded-lg overflow-hidden bg-brand-midnight/50"
        style={{ height: 160, width: '100%' }}
      >
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
          minZoom={0.5}
          maxZoom={1.5}
          style={{ width: '100%', height: '100%' }}
        >
          <Background color="rgba(225, 225, 230, 0.05)" gap={20} />
        </ReactFlow>
      </div>
    </div>
  );
}
