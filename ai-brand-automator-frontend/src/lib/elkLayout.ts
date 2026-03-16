/**
 * elkLayout — elk.js auto-layout for the workflow canvas.
 *
 * Uses the `elk.layered` algorithm for left-to-right hierarchical layout.
 * Runs on main thread (sufficient for ≤50 nodes).
 */

import ELK, { type ElkNode } from 'elkjs/lib/elk.bundled';
import type { Node, Edge } from '@xyflow/react';

const elk = new ELK();

const NODE_WIDTH = 200;
const NODE_HEIGHT = 100;

interface LayoutResult {
  nodes: Node[];
  edges: Edge[];
}

export async function computeElkLayout(
  nodes: Node[],
  edges: Edge[],
  direction: 'RIGHT' | 'DOWN' = 'RIGHT',
): Promise<LayoutResult> {
  if (nodes.length === 0) {
    return { nodes: [], edges };
  }

  const graph: ElkNode = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': direction,
      'elk.spacing.nodeNode': '60',
      'elk.layered.spacing.nodeNodeBetweenLayers': '80',
      'elk.padding': '[top=40,left=40,bottom=40,right=40]',
      'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    },
    children: nodes.map((n) => ({
      id: n.id,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
    })),
  };

  const layouted = await elk.layout(graph);

  const positionedNodes = nodes.map((n) => {
    const elkChild = layouted.children?.find((c) => c.id === n.id);
    return {
      ...n,
      position: {
        x: elkChild?.x ?? n.position.x,
        y: elkChild?.y ?? n.position.y,
      },
    };
  });

  return { nodes: positionedNodes, edges };
}
