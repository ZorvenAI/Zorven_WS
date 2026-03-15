/**
 * useWorkflowStore — useReducer-based state management for the workflow canvas.
 *
 * Manages nodes, edges, viewport, dirty state, and undo/redo stacks.
 * Provides a dispatch function and derived helpers for the canvas editor.
 *
 * Phase 2: Full editing support with undo/redo (max 50 operations).
 */

'use client';

import { useReducer, useCallback, useRef, useEffect } from 'react';
import type { Node, Edge, Viewport } from '@xyflow/react';
import type { AgentNodeData } from '@/components/workspace/AgentNode';
import type { ManifestGraphData, ManifestNode } from '@/types/orchestration';
import type { LayoutData } from '@/types/workspace';

// ── Constants ──

const MAX_UNDO_STACK = 50;
const AUTOSAVE_DEBOUNCE_MS = 2000;

// ── Action Types ──

export type WorkflowAction =
  | { type: 'LOAD'; nodes: Node[]; edges: Edge[] }
  | { type: 'ADD_NODE'; node: Node }
  | { type: 'REMOVE_NODE'; nodeId: string }
  | { type: 'ADD_EDGE'; edge: Edge }
  | { type: 'REMOVE_EDGE'; edgeId: string }
  | { type: 'MOVE_NODE'; nodeId: string; x: number; y: number }
  | { type: 'UPDATE_NODES'; nodes: Node[] }
  | { type: 'UPDATE_EDGES'; edges: Edge[] }
  | { type: 'SET_VIEWPORT'; viewport: Viewport }
  | { type: 'UNDO' }
  | { type: 'REDO' }
  | { type: 'MARK_SAVED' };

// ── State ──

interface UndoEntry {
  nodes: Node[];
  edges: Edge[];
}

export interface WorkflowState {
  nodes: Node[];
  edges: Edge[];
  viewport: Viewport;
  isDirty: boolean;
  undoStack: UndoEntry[];
  redoStack: UndoEntry[];
}

const initialState: WorkflowState = {
  nodes: [],
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
  isDirty: false,
  undoStack: [],
  redoStack: [],
};

// ── Reducer ──

function pushUndo(state: WorkflowState): UndoEntry[] {
  const entry: UndoEntry = { nodes: state.nodes, edges: state.edges };
  const stack = [...state.undoStack, entry];
  if (stack.length > MAX_UNDO_STACK) stack.shift();
  return stack;
}

function workflowReducer(
  state: WorkflowState,
  action: WorkflowAction,
): WorkflowState {
  switch (action.type) {
    case 'LOAD':
      return {
        ...state,
        nodes: action.nodes,
        edges: action.edges,
        isDirty: false,
        undoStack: [],
        redoStack: [],
      };

    case 'ADD_NODE':
      return {
        ...state,
        undoStack: pushUndo(state),
        redoStack: [],
        nodes: [...state.nodes, action.node],
        isDirty: true,
      };

    case 'REMOVE_NODE': {
      const nodeId = action.nodeId;
      return {
        ...state,
        undoStack: pushUndo(state),
        redoStack: [],
        nodes: state.nodes.filter((n) => n.id !== nodeId),
        edges: state.edges.filter(
          (e) => e.source !== nodeId && e.target !== nodeId,
        ),
        isDirty: true,
      };
    }

    case 'ADD_EDGE':
      return {
        ...state,
        undoStack: pushUndo(state),
        redoStack: [],
        edges: [...state.edges, action.edge],
        isDirty: true,
      };

    case 'REMOVE_EDGE':
      return {
        ...state,
        undoStack: pushUndo(state),
        redoStack: [],
        edges: state.edges.filter((e) => e.id !== action.edgeId),
        isDirty: true,
      };

    case 'MOVE_NODE':
      return {
        ...state,
        nodes: state.nodes.map((n) =>
          n.id === action.nodeId
            ? { ...n, position: { x: action.x, y: action.y } }
            : n,
        ),
        isDirty: true,
      };

    case 'UPDATE_NODES':
      return {
        ...state,
        nodes: action.nodes,
        isDirty: true,
      };

    case 'UPDATE_EDGES':
      return {
        ...state,
        edges: action.edges,
        isDirty: true,
      };

    case 'SET_VIEWPORT':
      return { ...state, viewport: action.viewport };

    case 'UNDO': {
      if (state.undoStack.length === 0) return state;
      const prev = state.undoStack[state.undoStack.length - 1];
      const current: UndoEntry = { nodes: state.nodes, edges: state.edges };
      return {
        ...state,
        nodes: prev.nodes,
        edges: prev.edges,
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [...state.redoStack, current],
        isDirty: true,
      };
    }

    case 'REDO': {
      if (state.redoStack.length === 0) return state;
      const next = state.redoStack[state.redoStack.length - 1];
      const current: UndoEntry = { nodes: state.nodes, edges: state.edges };
      return {
        ...state,
        nodes: next.nodes,
        edges: next.edges,
        undoStack: [...state.undoStack, current],
        redoStack: state.redoStack.slice(0, -1),
        isDirty: true,
      };
    }

    case 'MARK_SAVED':
      return { ...state, isDirty: false };

    default:
      return state;
  }
}

// ── Hook ──

export function useWorkflowStore(workflowId: string | null) {
  const [state, dispatch] = useReducer(workflowReducer, initialState);
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced localStorage save for crash recovery
  useEffect(() => {
    if (!workflowId || !state.isDirty) return;

    if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    autosaveTimer.current = setTimeout(() => {
      try {
        const key = `workflow-draft-${workflowId}`;
        const draft = {
          nodes: state.nodes.map((n) => ({
            id: n.id,
            position: n.position,
            data: n.data,
            type: n.type,
          })),
          edges: state.edges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
          })),
          savedAt: Date.now(),
        };
        localStorage.setItem(key, JSON.stringify(draft));
      } catch {
        // localStorage may be full or unavailable
      }
    }, AUTOSAVE_DEBOUNCE_MS);

    return () => {
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    };
  }, [workflowId, state.isDirty, state.nodes, state.edges]);

  // ── Helpers ──

  const canUndo = state.undoStack.length > 0;
  const canRedo = state.redoStack.length > 0;

  const undo = useCallback(() => dispatch({ type: 'UNDO' }), []);
  const redo = useCallback(() => dispatch({ type: 'REDO' }), []);
  const markSaved = useCallback(() => dispatch({ type: 'MARK_SAVED' }), []);

  /** Convert current state back to ManifestGraphData for saving. */
  const toManifestData = useCallback((): ManifestGraphData => {
    const nodes: ManifestNode[] = state.nodes.map((n) => {
      const d = n.data as AgentNodeData;
      return {
        id: n.id,
        type: d.agentType,
        ...(d.agentType === 'internal' ? { handler: d.handler ?? d.agentId } : {}),
        ...(d.agentType === 'external' && d.url ? { url: d.url } : {}),
        label: d.label,
      };
    });

    const edges: [string, string][] = state.edges.map((e) => [
      e.source,
      e.target,
    ]);

    return { nodes, edges };
  }, [state.nodes, state.edges]);

  /** Convert current node positions to LayoutData for saving. */
  const toLayoutData = useCallback((): LayoutData => {
    const nodePositions: Record<string, { x: number; y: number }> = {};
    for (const n of state.nodes) {
      nodePositions[n.id] = { x: n.position.x, y: n.position.y };
    }
    return { nodes: nodePositions, viewport: state.viewport };
  }, [state.nodes, state.viewport]);

  /** Clear the crash-recovery draft from localStorage. */
  const clearDraft = useCallback(() => {
    if (workflowId) {
      try {
        localStorage.removeItem(`workflow-draft-${workflowId}`);
      } catch {
        // ignore
      }
    }
  }, [workflowId]);

  return {
    state,
    dispatch,
    canUndo,
    canRedo,
    undo,
    redo,
    markSaved,
    toManifestData,
    toLayoutData,
    clearDraft,
  };
}
