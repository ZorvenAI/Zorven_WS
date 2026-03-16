/**
 * WorkflowInfoModal — "Learn More" popup for a workflow.
 *
 * Shows workflow details: all agents, pipeline flow,
 * execution stats, and timestamps.
 */

'use client';

import { useEffect, useCallback } from 'react';
import { X, ArrowRight } from 'lucide-react';
import type { UserWorkflowDetail } from '@/types/workspace';
import type { AgentCatalogEntry } from '@/types/workspace';

interface WorkflowInfoModalProps {
  workflow: UserWorkflowDetail;
  agents: AgentCatalogEntry[];
  onClose: () => void;
}

// ── Helpers ──

const SOURCE_LABELS: Record<string, string> = {
  created: 'Manually Created',
  cloned: 'Cloned',
  template: 'From Template',
  chat: 'From Chat',
};

const STATUS_COLORS: Record<string, string> = {
  queued: 'bg-amber-400/20 text-amber-300',
  running: 'bg-brand-electric/20 text-brand-electric',
  completed: 'bg-emerald-400/20 text-emerald-300',
  failed: 'bg-red-400/20 text-red-300',
};

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ── Component ──

export default function WorkflowInfoModal({
  workflow,
  agents,
  onClose,
}: WorkflowInfoModalProps) {
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

  const manifestNodes = workflow.manifest_data?.nodes ?? [];
  const manifestEdges = workflow.manifest_data?.edges ?? [];

  // Build agent lookup
  const agentMap = new Map(agents.map((a) => [a.id, a]));

  // Build flow text: follow edges to show pipeline path
  const flowSegments = manifestEdges.map(
    ([src, dst]) => `${humanLabel(src)} → ${humanLabel(dst)}`,
  );

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
              {workflow.name}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-brand-ghost/10 text-brand-ghost">
                {SOURCE_LABELS[workflow.source] ?? workflow.source}
              </span>
              {workflow.last_job_status && (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded ${STATUS_COLORS[workflow.last_job_status] ?? ''}`}
                >
                  {workflow.last_job_status}
                </span>
              )}
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
          {/* Description */}
          {workflow.description && (
            <Section title="Description">
              <p className="text-xs text-brand-silver/70 leading-relaxed">
                {workflow.description}
              </p>
            </Section>
          )}

          {/* Agents in this workflow */}
          {manifestNodes.length > 0 && (
            <Section title={`Agents in this workflow (${manifestNodes.length})`}>
              <div className="space-y-1.5">
                {manifestNodes.map((node) => {
                  const catalogAgent = agentMap.get(node.id);
                  const label =
                    node.label ?? catalogAgent?.label ?? humanLabel(node.id);
                  const desc =
                    catalogAgent?.description ?? '';
                  return (
                    <div
                      key={node.id}
                      className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-white/5"
                    >
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-medium text-brand-silver truncate block">
                          {label}
                        </span>
                        {desc && (
                          <span className="text-[10px] text-brand-silver/40 truncate block">
                            {desc}
                          </span>
                        )}
                      </div>
                      <span
                        className={`text-[8px] px-1 py-0.5 rounded shrink-0 ${
                          node.type === 'external'
                            ? 'bg-brand-electric/10 text-brand-electric'
                            : 'bg-brand-ghost/10 text-brand-ghost'
                        }`}
                      >
                        {node.type === 'external' ? 'EXT' : 'INT'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </Section>
          )}

          {/* Pipeline flow */}
          {flowSegments.length > 0 && (
            <Section title="Pipeline flow">
              <div className="space-y-1">
                {flowSegments.map((segment, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-1.5 text-xs text-brand-silver/60"
                  >
                    <ArrowRight className="w-3 h-3 text-brand-electric/50 shrink-0" />
                    <span>{segment}</span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Execution stats */}
          <Section title="Execution stats">
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Total runs" value={String(workflow.execution_count)} />
              <Stat
                label="Last executed"
                value={formatDate(workflow.last_executed_at)}
              />
              <Stat
                label="Last status"
                value={workflow.last_job_status ?? 'Never run'}
              />
              <Stat label="Source" value={SOURCE_LABELS[workflow.source] ?? workflow.source} />
            </div>
          </Section>

          {/* Timestamps */}
          <Section title="Timestamps">
            <div className="space-y-1.5 text-[11px]">
              <div className="flex items-baseline gap-2">
                <span className="text-brand-silver/40 shrink-0">Created:</span>
                <span className="text-brand-silver/70">
                  {formatDate(workflow.created_at)}
                </span>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-brand-silver/40 shrink-0">Updated:</span>
                <span className="text-brand-silver/70">
                  {formatDate(workflow.updated_at)}
                </span>
              </div>
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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-2 py-1.5 rounded-lg bg-white/5">
      <p className="text-[10px] text-brand-silver/40">{label}</p>
      <p className="text-xs text-brand-silver/70 capitalize">{value}</p>
    </div>
  );
}

function humanLabel(nodeId: string): string {
  return nodeId.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
