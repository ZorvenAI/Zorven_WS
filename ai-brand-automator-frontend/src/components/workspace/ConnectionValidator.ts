/**
 * ConnectionValidator — validates edge connections in the workflow canvas.
 *
 * Prevents: self-loops, duplicate edges, and cycles (BFS from target to source).
 */

import type { Edge, Connection } from '@xyflow/react';

/**
 * Check whether a proposed connection is valid.
 * Returns an error string if invalid, or null if valid.
 */
export function validateConnection(
  connection: Connection,
  edges: Edge[],
): string | null {
  const { source, target } = connection;
  if (!source || !target) return 'Missing source or target';

  // No self-loops
  if (source === target) return 'Cannot connect a node to itself';

  // No duplicate edges
  const duplicate = edges.some(
    (e) => e.source === source && e.target === target,
  );
  if (duplicate) return 'This connection already exists';

  // No cycles — BFS from target following existing edges + proposed edge
  if (wouldCreateCycle(source, target, edges)) {
    return 'This connection would create a cycle';
  }

  return null;
}

/**
 * BFS from `target` to check if `source` is reachable (which would mean a cycle).
 */
function wouldCreateCycle(
  source: string,
  target: string,
  edges: Edge[],
): boolean {
  // Build adjacency list from existing edges only.
  // We check: does adding source→target create a cycle?
  // Yes, iff there's already a path from target→source in existing edges.
  const adj = new Map<string, string[]>();
  for (const e of edges) {
    const list = adj.get(e.source) ?? [];
    list.push(e.target);
    adj.set(e.source, list);
  }
  const visited = new Set<string>();
  const queue = [target];
  visited.add(target);

  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const neighbor of adj.get(current) ?? []) {
      if (neighbor === source) return true;
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push(neighbor);
      }
    }
  }

  return false;
}

/**
 * Convenience wrapper for React Flow's isValidConnection callback.
 */
export function isValidConnection(
  connection: Connection,
  edges: Edge[],
): boolean {
  return validateConnection(connection, edges) === null;
}
