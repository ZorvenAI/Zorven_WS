/**
 * AgentCatalogPanel — grid of draggable agent cards for the workflow canvas.
 *
 * Agents are dragged from here onto the canvas. Each card shows the agent
 * name, description, type badge, and health dot. Uses HTML5 drag & drop
 * with `application/reactflow` MIME type for React Flow compatibility.
 */

'use client';

import { useState, useMemo, useEffect } from 'react';
import { Search, GripVertical } from 'lucide-react';
import { listAgents } from '@/lib/workspace';
import type { AgentCatalogEntry, AgentHealth } from '@/types/workspace';

// ── Health badge ──

const HEALTH_COLOR: Record<AgentHealth, string> = {
  healthy: 'bg-emerald-400',
  unhealthy: 'bg-amber-400',
  unknown: 'bg-brand-silver/30',
};

// ── Component ──

export default function AgentCatalogPanel() {
  const [agents, setAgents] = useState<AgentCatalogEntry[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function fetchAgents() {
      try {
        setIsLoading(true);
        const data = await listAgents();
        if (!cancelled) setAgents(data);
      } catch (err) {
        console.error('Failed to load agent catalog:', err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    fetchAgents();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return agents;
    const q = searchQuery.toLowerCase();
    return agents.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.label.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q),
    );
  }, [agents, searchQuery]);

  const onDragStart = (
    event: React.DragEvent<HTMLDivElement>,
    agent: AgentCatalogEntry,
  ) => {
    event.dataTransfer.setData(
      'application/reactflow',
      JSON.stringify(agent),
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="px-3 pt-3 pb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brand-silver/40" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search agents..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg text-brand-silver placeholder:text-brand-silver/30 focus:outline-none focus:border-brand-electric/50"
          />
        </div>
      </div>

      <p className="px-3 pb-1 text-[10px] text-brand-silver/40">
        Drag agents onto the canvas
      </p>

      {/* Agent grid */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {isLoading ? (
          <div className="space-y-2 p-2">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-14 rounded-lg bg-white/5 animate-pulse"
              />
            ))}
          </div>
        ) : (
          <div className="space-y-1">
            {filtered.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onDragStart={onDragStart}
              />
            ))}
            {filtered.length === 0 && (
              <p className="text-xs text-brand-silver/30 text-center py-4">
                No agents found
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Agent card ──

function AgentCard({
  agent,
  onDragStart,
}: {
  agent: AgentCatalogEntry;
  onDragStart: (e: React.DragEvent<HTMLDivElement>, agent: AgentCatalogEntry) => void;
}) {
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, agent)}
      className="flex items-center gap-2 px-2 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-transparent hover:border-brand-electric/20 cursor-grab active:cursor-grabbing transition-colors group"
    >
      <GripVertical className="w-3 h-3 text-brand-silver/20 group-hover:text-brand-silver/40 shrink-0" />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-brand-silver truncate">
            {agent.label}
          </span>
          <div
            className={`w-1.5 h-1.5 rounded-full shrink-0 ${HEALTH_COLOR[agent.health]}`}
            title={`Health: ${agent.health}`}
          />
        </div>
        <p className="text-[10px] text-brand-silver/40 truncate">
          {agent.description}
        </p>
      </div>

      <span
        className={`text-[8px] px-1 py-0.5 rounded shrink-0 ${
          agent.type === 'external'
            ? 'bg-brand-electric/10 text-brand-electric'
            : 'bg-brand-ghost/10 text-brand-ghost'
        }`}
      >
        {agent.type === 'external' ? 'EXT' : 'INT'}
      </span>
    </div>
  );
}
