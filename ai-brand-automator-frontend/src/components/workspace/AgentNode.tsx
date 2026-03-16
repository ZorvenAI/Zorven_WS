/**
 * AgentNode — custom React Flow node for the workspace canvas.
 *
 * Renders agent name, description, health badge, and execution
 * status overlay with animations matching PipelineGraph patterns.
 */

'use client';

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  Info,
  Trash2,
  Search,
  BarChart3,
  Swords,
  UserSearch,
  TrendingUp,
  MessageCircle,
  Gem,
  PenTool,
  Share2,
  Database,
  Briefcase,
  Route,
  LayoutDashboard,
  Target,
  FileText,
  Users,
  CalendarDays,
  Calendar,
  type LucideIcon,
} from 'lucide-react';
import type { AgentHealth } from '@/types/workspace';

// ── Types ──

export interface AgentNodeData {
  label: string;
  agentId: string;
  description?: string;
  agentType: 'internal' | 'external';
  url?: string;
  handler?: string;
  health?: AgentHealth;
  status?: 'pending' | 'running' | 'done' | 'failed';
  icon?: string;
  [key: string]: unknown;
}

// ── Icon mapping ──

const ICON_MAP: Record<string, LucideIcon> = {
  search: Search,
  'bar-chart-3': BarChart3,
  swords: Swords,
  'user-search': UserSearch,
  'trending-up': TrendingUp,
  'message-circle': MessageCircle,
  gem: Gem,
  'pen-tool': PenTool,
  'share-2': Share2,
  database: Database,
  briefcase: Briefcase,
  route: Route,
  'layout-dashboard': LayoutDashboard,
  target: Target,
  'file-text': FileText,
  users: Users,
  'calendar-days': CalendarDays,
  calendar: Calendar,
};

// ── Status styling ──

const STATUS_BORDER: Record<string, string> = {
  pending: 'border-brand-silver/30',
  running: 'border-brand-electric animate-pulse',
  done: 'border-emerald-400',
  failed: 'border-red-400',
};

const STATUS_ICON: Record<string, React.ReactNode> = {
  pending: <Circle className="w-3.5 h-3.5 text-brand-silver/40" />,
  running: <Loader2 className="w-3.5 h-3.5 text-brand-electric animate-spin" />,
  done: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />,
  failed: <XCircle className="w-3.5 h-3.5 text-red-400" />,
};

// ── Health badge ──

const HEALTH_COLOR: Record<AgentHealth, string> = {
  healthy: 'bg-emerald-400',
  unhealthy: 'bg-amber-400',
  unknown: 'bg-brand-silver/30',
};

// ── Component ──

function AgentNodeComponent({ id, data, isConnectable }: NodeProps) {
  const nodeData = data as unknown as AgentNodeData;
  const status = nodeData.status ?? 'pending';
  const health = nodeData.health ?? 'unknown';
  const IconComponent = nodeData.icon ? ICON_MAP[nodeData.icon] : null;

  return (
    <div
      className={`
        group relative rounded-xl border-2 bg-white/5 backdrop-blur-sm
        px-4 py-3 min-w-[160px] max-w-[200px]
        ${STATUS_BORDER[status] ?? STATUS_BORDER.pending}
      `}
    >
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={isConnectable}
        className="!bg-brand-electric/40 !w-3 !h-3 !border !border-brand-electric/60 hover:!bg-brand-electric/80"
      />

      {/* Header: icon + label + type badge + health */}
      <div className="flex items-center gap-1.5">
        {IconComponent && (
          <IconComponent className="w-4 h-4 text-brand-electric shrink-0" />
        )}
        <span className="text-sm font-medium text-brand-silver truncate flex-1">
          {nodeData.label}
        </span>
        <span
          className={`
            text-[8px] px-1 py-0.5 rounded shrink-0
            ${nodeData.agentType === 'external' ? 'bg-brand-electric/10 text-brand-electric' : 'bg-brand-ghost/10 text-brand-ghost'}
          `}
        >
          {nodeData.agentType === 'external' ? 'EXT' : 'INT'}
        </span>
        <div
          className={`w-2 h-2 rounded-full shrink-0 ${HEALTH_COLOR[health]}`}
          title={`Health: ${health}`}
        />
      </div>

      {/* Description */}
      {nodeData.description && (
        <p className="mt-1 text-[10px] text-brand-silver/50 line-clamp-2">
          {nodeData.description}
        </p>
      )}

      {/* Status indicator + info button */}
      <div className="mt-1.5 flex items-center gap-1.5">
        {STATUS_ICON[status]}
        <span className="text-[10px] text-brand-silver/40 capitalize flex-1">
          {status === 'running' ? 'Running\u2026' : status}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            window.dispatchEvent(
              new CustomEvent('agent-info', { detail: nodeData }),
            );
          }}
          className="p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/10"
          title="Learn more"
        >
          <Info className="w-3.5 h-3.5 text-brand-silver/40 hover:text-brand-electric" />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            window.dispatchEvent(
              new CustomEvent('agent-delete', { detail: { nodeId: id } }),
            );
          }}
          className="p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/10"
          title="Remove agent"
        >
          <Trash2 className="w-3.5 h-3.5 text-brand-silver/40 hover:text-red-400" />
        </button>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        isConnectable={isConnectable}
        className="!bg-brand-electric/40 !w-3 !h-3 !border !border-brand-electric/60 hover:!bg-brand-electric/80"
      />
    </div>
  );
}

const AgentNode = memo(AgentNodeComponent);
export default AgentNode;
