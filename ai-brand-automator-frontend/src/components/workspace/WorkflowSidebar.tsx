/**
 * WorkflowSidebar — left panel of the workspace.
 *
 * Tabs: My Workflows, Agents, Templates
 * Searchable workflow list with status badges and favorites.
 */

'use client';

import { useState, useMemo } from 'react';
import {
  Search,
  Star,
  StarOff,
  Plus,
  Clock,
  ChevronRight,
  FileCode,
  Copy,
  Trash2,
  Pencil,
  Check,
  X,
} from 'lucide-react';
import type { UserWorkflowSummary } from '@/types/workspace';
import type { PipelineManifestListItem, JobStatus } from '@/types/orchestration';
import AgentCatalogPanel from './AgentCatalogPanel';

// ── Types ──

interface WorkflowSidebarProps {
  workflows: UserWorkflowSummary[];
  selectedId: string | null;
  onSelect: (workflowId: string) => void;
  onCreateNew: () => void;
  onToggleFavorite: (workflowId: string, isFavorite: boolean) => void;
  onDelete: (workflowId: string) => void;
  onRename: (workflowId: string, newName: string) => void;
  onCloneTemplate?: (templateId: string, templateName: string) => void;
  templates?: PipelineManifestListItem[];
  isLoading?: boolean;
}

type TabId = 'workflows' | 'agents' | 'templates';

// ── Status badge ──

const STATUS_STYLES: Record<JobStatus, string> = {
  queued: 'bg-amber-400/20 text-amber-300',
  running: 'bg-brand-electric/20 text-brand-electric',
  completed: 'bg-emerald-400/20 text-emerald-300',
  failed: 'bg-red-400/20 text-red-300',
};

function StatusDot({ status }: { status: JobStatus | null }) {
  if (!status) return null;
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-medium ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

// ── Component ──

export default function WorkflowSidebar({
  workflows,
  selectedId,
  onSelect,
  onCreateNew,
  onToggleFavorite,
  onDelete,
  onRename,
  onCloneTemplate,
  templates = [],
  isLoading = false,
}: WorkflowSidebarProps) {
  const [activeTab, setActiveTab] = useState<TabId>('workflows');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredWorkflows = useMemo(() => {
    if (!searchQuery.trim()) return workflows;
    const q = searchQuery.toLowerCase();
    return workflows.filter(
      (w) =>
        w.name.toLowerCase().includes(q) ||
        w.description.toLowerCase().includes(q),
    );
  }, [workflows, searchQuery]);

  const filteredTemplates = useMemo(() => {
    if (!searchQuery.trim()) return templates;
    const q = searchQuery.toLowerCase();
    return templates.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        (t.description ?? '').toLowerCase().includes(q),
    );
  }, [templates, searchQuery]);

  const favorites = useMemo(
    () => filteredWorkflows.filter((w) => w.is_favorite),
    [filteredWorkflows],
  );
  const rest = useMemo(
    () => filteredWorkflows.filter((w) => !w.is_favorite),
    [filteredWorkflows],
  );

  return (
    <div className="flex flex-col h-full">
      {/* Tabs */}
      <div className="flex border-b border-white/10 px-1">
        {(['workflows', 'agents', 'templates'] as TabId[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2 text-xs font-medium transition-colors ${
              activeTab === tab
                ? 'text-brand-electric border-b-2 border-brand-electric'
                : 'text-brand-silver/50 hover:text-brand-silver'
            }`}
          >
            {tab === 'workflows' ? 'Workflows' : tab === 'agents' ? 'Agents' : 'Templates'}
          </button>
        ))}
      </div>

      {/* Agent Catalog tab */}
      {activeTab === 'agents' && <AgentCatalogPanel />}

      {/* Workflows + Templates tabs share search */}
      {activeTab !== 'agents' && (
        <>
          {/* Search */}
          <div className="px-3 pt-3 pb-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brand-silver/40" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={activeTab === 'workflows' ? 'Search workflows...' : 'Search templates...'}
                className="w-full pl-8 pr-3 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg text-brand-silver placeholder:text-brand-silver/30 focus:outline-none focus:border-brand-electric/50"
              />
            </div>
          </div>

          {/* New Workflow button (workflows tab only) */}
          {activeTab === 'workflows' && (
            <div className="px-3 pb-2">
              <button
                onClick={onCreateNew}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-brand-electric bg-brand-electric/10 hover:bg-brand-electric/20 rounded-lg transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                New Workflow
              </button>
            </div>
          )}

          {/* Content list */}
          <div className="flex-1 overflow-y-auto px-2">
            {isLoading ? (
              <div className="space-y-2 p-2">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-16 rounded-lg bg-white/5 animate-pulse"
                  />
                ))}
              </div>
            ) : activeTab === 'workflows' ? (
              <>
                {/* Favorites */}
                {favorites.length > 0 && (
                  <div className="mb-3">
                    <p className="px-2 py-1 text-[10px] font-medium text-brand-silver/40 uppercase tracking-wider">
                      Favorites
                    </p>
                    {favorites.map((w) => (
                      <WorkflowItem
                        key={w.workflow_id}
                        workflow={w}
                        isSelected={selectedId === w.workflow_id}
                        onSelect={onSelect}
                        onToggleFavorite={onToggleFavorite}
                        onDelete={onDelete}
                        onRename={onRename}
                      />
                    ))}
                  </div>
                )}

                {/* All workflows */}
                <div>
                  {favorites.length > 0 && (
                    <p className="px-2 py-1 text-[10px] font-medium text-brand-silver/40 uppercase tracking-wider">
                      All Workflows
                    </p>
                  )}
                  {rest.map((w) => (
                    <WorkflowItem
                      key={w.workflow_id}
                      workflow={w}
                      isSelected={selectedId === w.workflow_id}
                      onSelect={onSelect}
                      onToggleFavorite={onToggleFavorite}
                      onDelete={onDelete}
                      onRename={onRename}
                    />
                  ))}
                  {filteredWorkflows.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-8 text-brand-silver/30">
                      <FileCode className="w-8 h-8 mb-2" />
                      <p className="text-xs">No workflows found</p>
                    </div>
                  )}
                </div>
              </>
            ) : (
              /* Templates tab */
              <div>
                {filteredTemplates.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-brand-silver/30">
                    <FileCode className="w-8 h-8 mb-2" />
                    <p className="text-xs">No templates available</p>
                  </div>
                ) : (
                  filteredTemplates.map((t) => (
                    <TemplateItem
                      key={t.id}
                      template={t}
                      onClone={onCloneTemplate}
                    />
                  ))
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Workflow list item ──

function WorkflowItem({
  workflow,
  isSelected,
  onSelect,
  onToggleFavorite,
  onDelete,
  onRename,
}: {
  workflow: UserWorkflowSummary;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onToggleFavorite: (id: string, isFavorite: boolean) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, newName: string) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(workflow.name);

  const handleStartRename = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditName(workflow.name);
    setIsEditing(true);
  };

  const handleConfirmRename = () => {
    const trimmed = editName.trim();
    if (trimmed && trimmed !== workflow.name) {
      onRename(workflow.workflow_id, trimmed);
    }
    setIsEditing(false);
  };

  const handleCancelRename = () => {
    setEditName(workflow.name);
    setIsEditing(false);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm(`Delete "${workflow.name}"? This cannot be undone.`)) {
      onDelete(workflow.workflow_id);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !isEditing && onSelect(workflow.workflow_id)}
      onKeyDown={(e) => { if (!isEditing && (e.key === 'Enter' || e.key === ' ')) onSelect(workflow.workflow_id); }}
      className={`
        w-full text-left px-2 py-2 rounded-lg mb-0.5 transition-colors group cursor-pointer
        ${isSelected ? 'bg-brand-electric/10 border border-brand-electric/30' : 'hover:bg-white/5 border border-transparent'}
      `}
    >
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            {isEditing ? (
              <div className="flex items-center gap-1 flex-1" onClick={(e) => e.stopPropagation()}>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => {
                    e.stopPropagation();
                    if (e.key === 'Enter') handleConfirmRename();
                    if (e.key === 'Escape') handleCancelRename();
                  }}
                  autoFocus
                  className="flex-1 text-xs font-medium bg-white/10 border border-brand-electric/50 rounded px-1.5 py-0.5 text-brand-silver focus:outline-none focus:border-brand-electric min-w-0"
                />
                <button onClick={handleConfirmRename} className="p-0.5 rounded hover:bg-white/10">
                  <Check className="w-3 h-3 text-emerald-400" />
                </button>
                <button onClick={handleCancelRename} className="p-0.5 rounded hover:bg-white/10">
                  <X className="w-3 h-3 text-red-400" />
                </button>
              </div>
            ) : (
              <>
                <span className="text-xs font-medium text-brand-silver truncate">
                  {workflow.name}
                </span>
                <StatusDot status={workflow.last_job_status} />
              </>
            )}
          </div>
          {!isEditing && workflow.description && (
            <p className="text-[10px] text-brand-silver/40 truncate mt-0.5">
              {workflow.description}
            </p>
          )}
          {!isEditing && (
            <div className="flex items-center gap-2 mt-1 text-[9px] text-brand-silver/30">
              <span className="flex items-center gap-0.5">
                <Clock className="w-2.5 h-2.5" />
                {workflow.execution_count} runs
              </span>
              <span>{workflow.source}</span>
            </div>
          )}
        </div>

        {!isEditing && (
          <div className="flex items-center gap-0.5 shrink-0">
            <button
              onClick={handleStartRename}
              className="p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/10"
              title="Rename"
            >
              <Pencil className="w-3 h-3 text-brand-silver/40" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onToggleFavorite(workflow.workflow_id, !workflow.is_favorite);
              }}
              className="p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/10"
            >
              {workflow.is_favorite ? (
                <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
              ) : (
                <StarOff className="w-3 h-3 text-brand-silver/30" />
              )}
            </button>
            <button
              onClick={handleDelete}
              className="p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/10"
              title="Delete"
            >
              <Trash2 className="w-3 h-3 text-red-400/60" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Template item ──

function TemplateItem({
  template,
  onClone,
}: {
  template: PipelineManifestListItem;
  onClone?: (templateId: string, templateName: string) => void;
}) {
  return (
    <div className="flex items-center gap-2 px-2 py-2 rounded-lg mb-0.5 hover:bg-white/5 border border-transparent group">
      <div className="flex-1 min-w-0">
        <span className="text-xs font-medium text-brand-silver truncate block">
          {template.name}
        </span>
        {template.description && (
          <p className="text-[10px] text-brand-silver/40 truncate mt-0.5">
            {template.description}
          </p>
        )}
      </div>
      {onClone && (
        <button
          onClick={() => onClone(String(template.id), template.name)}
          className="p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-brand-electric/10"
          title="Use template"
        >
          <Copy className="w-3.5 h-3.5 text-brand-electric" />
        </button>
      )}
    </div>
  );
}
