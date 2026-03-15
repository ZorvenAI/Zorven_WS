/**
 * WorkspaceLayout — resizable 3-panel container for the workspace.
 *
 * Left: Workflow browser + agent catalog (default 280px, resizable)
 * Center: Toolbar + React Flow canvas (flex-1)
 * Right: Results inspector (default 360px, resizable)
 *
 * Drag the dividers between panels to resize.
 */

'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { PanelLeft, PanelRight } from 'lucide-react';

// ── Constants ──

const LEFT_DEFAULT = 280;
const LEFT_MIN = 200;
const LEFT_MAX = 480;

const RIGHT_DEFAULT = 360;
const RIGHT_MIN = 280;
const RIGHT_MAX = 640;

// ── Props ──

interface WorkspaceLayoutProps {
  leftPanel: React.ReactNode;
  centerPanel: React.ReactNode;
  toolbar?: React.ReactNode;
  rightPanel?: React.ReactNode;
}

// ── Resize handle ──

function ResizeHandle({
  side,
  onMouseDown,
}: {
  side: 'left' | 'right';
  onMouseDown: (e: React.MouseEvent) => void;
}) {
  return (
    <div
      onMouseDown={onMouseDown}
      className={`
        shrink-0 w-1 cursor-col-resize group relative z-10
        ${side === 'left' ? 'border-r border-white/10' : 'border-l border-white/10'}
      `}
    >
      {/* Wider invisible hit area */}
      <div className="absolute inset-y-0 -left-1 -right-1" />
      {/* Visible highlight on hover / drag */}
      <div className="absolute inset-y-0 left-0 right-0 group-hover:bg-brand-electric/40 transition-colors" />
    </div>
  );
}

// ── Component ──

export default function WorkspaceLayout({
  leftPanel,
  centerPanel,
  toolbar,
  rightPanel,
}: WorkspaceLayoutProps) {
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(false);
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT);

  // Refs for drag state (avoid re-renders during drag)
  const dragging = useRef<'left' | 'right' | null>(null);
  const startX = useRef(0);
  const startWidth = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const toggleLeft = useCallback(() => setLeftOpen((p) => !p), []);
  const toggleRight = useCallback(() => setRightOpen((p) => !p), []);

  // ── Drag handlers ──

  const handleMouseDown = useCallback(
    (side: 'left' | 'right') => (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = side;
      startX.current = e.clientX;
      startWidth.current = side === 'left' ? leftWidth : rightWidth;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    },
    [leftWidth, rightWidth],
  );

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;

      if (dragging.current === 'left') {
        const newWidth = Math.min(LEFT_MAX, Math.max(LEFT_MIN, startWidth.current + delta));
        setLeftWidth(newWidth);
      } else {
        // Right panel: dragging left increases width
        const newWidth = Math.min(RIGHT_MAX, Math.max(RIGHT_MIN, startWidth.current - delta));
        setRightWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      if (!dragging.current) return;
      dragging.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  return (
    <div ref={containerRef} className="flex h-full w-full overflow-hidden">
      {/* Left Panel */}
      <div
        className={`
          shrink-0 bg-brand-surface/50 overflow-hidden
          ${leftOpen ? '' : 'w-0'}
        `}
        style={leftOpen ? { width: leftWidth } : undefined}
      >
        {leftOpen && (
          <div className="h-full overflow-hidden" style={{ width: leftWidth }}>
            {leftPanel}
          </div>
        )}
      </div>

      {/* Left resize handle */}
      {leftOpen && <ResizeHandle side="left" onMouseDown={handleMouseDown('left')} />}
      {/* Border when collapsed */}
      {!leftOpen && <div className="shrink-0 border-r border-white/10" />}

      {/* Center Panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar strip */}
        <div className="flex items-center gap-1 border-b border-white/10 bg-brand-surface/30">
          <div className="px-2 py-1">
            <button
              onClick={toggleLeft}
              className="p-1 rounded hover:bg-white/10 text-brand-silver/50 hover:text-brand-silver transition-colors"
              title={leftOpen ? 'Hide sidebar' : 'Show sidebar'}
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          </div>

          {/* Workflow toolbar */}
          {toolbar && <div className="flex-1">{toolbar}</div>}

          {!toolbar && <div className="flex-1" />}

          {rightPanel && (
            <div className="px-2 py-1">
              <button
                onClick={toggleRight}
                className="p-1 rounded hover:bg-white/10 text-brand-silver/50 hover:text-brand-silver transition-colors"
                title={rightOpen ? 'Hide inspector' : 'Show inspector'}
              >
                <PanelRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        {/* Canvas area */}
        <div className="flex-1 overflow-hidden">
          {centerPanel}
        </div>
      </div>

      {/* Right resize handle */}
      {rightPanel && rightOpen && <ResizeHandle side="right" onMouseDown={handleMouseDown('right')} />}
      {/* Border when collapsed */}
      {rightPanel && !rightOpen && <div className="shrink-0 border-l border-white/10" />}

      {/* Right Panel */}
      {rightPanel && (
        <div
          className={`
            shrink-0 bg-brand-surface/50 overflow-hidden
            ${rightOpen ? '' : 'w-0'}
          `}
          style={rightOpen ? { width: rightWidth } : undefined}
        >
          {rightOpen && (
            <div className="h-full overflow-hidden" style={{ width: rightWidth }}>
              {rightPanel}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
