/**
 * AgentInfoModal — "Learn More" popup for an agent.
 *
 * Shows what the agent does, when to use it, inputs/outputs,
 * and technical details (ID, type, URL/handler).
 */

'use client';

import { useEffect, useCallback } from 'react';
import { X } from 'lucide-react';
import type { AgentNodeData } from './AgentNode';
import type { AgentCatalogEntry, AgentHealth } from '@/types/workspace';
import { getAgentDetails } from '@/lib/agentDetails';

// ── Shared types ──

type AgentLike = AgentNodeData | AgentCatalogEntry;

interface AgentInfoModalProps {
  agent: AgentLike;
  onClose: () => void;
}

// ── Helpers ──

function resolveFields(agent: AgentLike) {
  // AgentNodeData uses `agentId` / `agentType`; AgentCatalogEntry uses `id` / `type`
  const id = 'agentId' in agent ? agent.agentId : agent.id;
  const name = 'agentId' in agent ? agent.label : agent.label;
  const description = agent.description ?? '';
  const agentType = 'agentType' in agent ? agent.agentType : agent.type;
  const health: AgentHealth =
    'health' in agent ? (agent.health ?? 'unknown') : 'unknown';
  const url = agent.url;
  const handler = agent.handler;
  return { id, name, description, agentType, health, url, handler };
}

const HEALTH_LABEL: Record<AgentHealth, { text: string; color: string }> = {
  healthy: { text: 'Healthy', color: 'text-emerald-400' },
  unhealthy: { text: 'Unhealthy', color: 'text-amber-400' },
  unknown: { text: 'Unknown', color: 'text-brand-silver/50' },
};

// ── Component ──

export default function AgentInfoModal({ agent, onClose }: AgentInfoModalProps) {
  const { id, name, description, agentType, health, url, handler } =
    resolveFields(agent);
  const details = getAgentDetails(id);

  // Close on ESC
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const healthInfo = HEALTH_LABEL[health];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

      {/* Dialog */}
      <div
        className="relative w-full max-w-lg mx-4 bg-brand-dark border border-white/10 rounded-xl shadow-2xl max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-5 pt-5 pb-3 border-b border-white/10">
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-heading font-semibold text-white truncate">
              {name}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded ${
                  agentType === 'external'
                    ? 'bg-brand-electric/10 text-brand-electric'
                    : 'bg-brand-ghost/10 text-brand-ghost'
                }`}
              >
                {agentType === 'external' ? 'External' : 'Internal'}
              </span>
              <span className={`text-[10px] ${healthInfo.color}`}>
                {healthInfo.text}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
          >
            <X className="w-4 h-4 text-brand-silver/60" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* What it does */}
          {description && (
            <Section title="What it does">
              <p className="text-xs text-brand-silver/70 leading-relaxed">
                {details?.details ?? description}
              </p>
            </Section>
          )}

          {/* When to use */}
          {details?.whenToUse && (
            <Section title="When to use">
              <p className="text-xs text-brand-silver/70 leading-relaxed">
                {details.whenToUse}
              </p>
            </Section>
          )}

          {/* Inputs */}
          {details?.inputs && details.inputs.length > 0 && (
            <Section title="Inputs">
              <ul className="space-y-1">
                {details.inputs.map((input) => (
                  <li
                    key={input}
                    className="flex items-start gap-2 text-xs text-brand-silver/70"
                  >
                    <span className="text-brand-electric mt-0.5">&#8227;</span>
                    {input}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Outputs */}
          {details?.outputs && details.outputs.length > 0 && (
            <Section title="Outputs">
              <ul className="space-y-1">
                {details.outputs.map((output) => (
                  <li
                    key={output}
                    className="flex items-start gap-2 text-xs text-brand-silver/70"
                  >
                    <span className="text-emerald-400 mt-0.5">&#8227;</span>
                    {output}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Technical details */}
          <Section title="Technical details">
            <div className="space-y-1.5 text-[11px]">
              <Detail label="Agent ID" value={id} />
              <Detail
                label="Type"
                value={agentType === 'external' ? 'External (microservice)' : 'Internal (handler)'}
              />
              {url && <Detail label="Service URL" value={url} />}
              {handler && <Detail label="Handler" value={handler} />}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ──

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-[11px] font-medium text-brand-silver/40 uppercase tracking-wider mb-1.5">
        {title}
      </h3>
      {children}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-brand-silver/40 shrink-0">{label}:</span>
      <span className="text-brand-silver/70 font-mono truncate">{value}</span>
    </div>
  );
}
