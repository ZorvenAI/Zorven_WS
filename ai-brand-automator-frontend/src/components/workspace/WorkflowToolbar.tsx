/**
 * WorkflowToolbar — toolbar strip for the workflow canvas.
 *
 * Actions: Save (Ctrl+S), Execute, Auto-Layout, Undo, Redo,
 * Zoom controls, Export/Import.
 */

'use client';

import {
  Save,
  Play,
  LayoutGrid,
  Undo2,
  Redo2,
  ZoomIn,
  ZoomOut,
  Download,
  Upload,
  Lock,
} from 'lucide-react';
import BrandContextSelector from '@/components/brand/BrandContextSelector';

interface WorkflowToolbarProps {
  onSave: () => void;
  onExecute: () => void;
  onAutoLayout: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onExport: () => void;
  onImport: () => void;
  canUndo: boolean;
  canRedo: boolean;
  isDirty: boolean;
  isSaving?: boolean;
  isReadonly?: boolean;
  lockHolder?: string | null;
}

function ToolbarButton({
  onClick,
  disabled,
  title,
  children,
  variant = 'default',
}: {
  onClick: () => void;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
  variant?: 'default' | 'primary' | 'success';
}) {
  const base =
    'p-1.5 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed';
  const styles = {
    default:
      'text-brand-silver/60 hover:text-brand-silver hover:bg-white/10',
    primary:
      'text-brand-electric hover:text-white hover:bg-brand-electric/20',
    success:
      'text-emerald-400 hover:text-emerald-300 hover:bg-emerald-400/10',
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`${base} ${styles[variant]}`}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="w-px h-5 bg-white/10 mx-1" />;
}

export default function WorkflowToolbar({
  onSave,
  onExecute,
  onAutoLayout,
  onUndo,
  onRedo,
  onZoomIn,
  onZoomOut,
  onExport,
  onImport,
  canUndo,
  canRedo,
  isDirty,
  isSaving = false,
  isReadonly = false,
  lockHolder,
}: WorkflowToolbarProps) {
  return (
    <div className="flex items-center gap-0.5 px-2 py-1">
      {/* Lock indicator */}
      {lockHolder && (
        <>
          <div className="flex items-center gap-1 px-2 py-1 rounded bg-amber-400/10 text-amber-300 text-[10px]">
            <Lock className="w-3 h-3" />
            <span>Locked by {lockHolder}</span>
          </div>
          <Divider />
        </>
      )}

      {/* Save */}
      <ToolbarButton
        onClick={onSave}
        disabled={!isDirty || isSaving || isReadonly}
        title="Save (Ctrl+S)"
        variant={isDirty ? 'primary' : 'default'}
      >
        <Save className="w-4 h-4" />
      </ToolbarButton>

      {/* Undo / Redo */}
      <ToolbarButton
        onClick={onUndo}
        disabled={!canUndo || isReadonly}
        title="Undo (Ctrl+Z)"
      >
        <Undo2 className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={onRedo}
        disabled={!canRedo || isReadonly}
        title="Redo (Ctrl+Shift+Z)"
      >
        <Redo2 className="w-4 h-4" />
      </ToolbarButton>

      <Divider />

      {/* Auto-Layout */}
      <ToolbarButton
        onClick={onAutoLayout}
        disabled={isReadonly}
        title="Auto-Layout"
      >
        <LayoutGrid className="w-4 h-4" />
      </ToolbarButton>

      {/* Zoom */}
      <ToolbarButton onClick={onZoomIn} title="Zoom In">
        <ZoomIn className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton onClick={onZoomOut} title="Zoom Out">
        <ZoomOut className="w-4 h-4" />
      </ToolbarButton>

      <Divider />

      {/* Execute */}
      <ToolbarButton
        onClick={onExecute}
        disabled={isReadonly}
        title="Execute Workflow"
        variant="success"
      >
        <Play className="w-4 h-4" />
      </ToolbarButton>

      <Divider />

      {/* Brand Context */}
      <BrandContextSelector />

      <div className="flex-1" />

      {/* Export / Import */}
      <ToolbarButton onClick={onExport} title="Export Workflow">
        <Download className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={onImport}
        disabled={isReadonly}
        title="Import Workflow"
      >
        <Upload className="w-4 h-4" />
      </ToolbarButton>
    </div>
  );
}
