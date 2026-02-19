/**
 * LogConsole — Live execution log panel.
 *
 * Renders timestamped, color-coded log entries derived from
 * progress changes between polling intervals. Scrolls to bottom
 * automatically as new entries arrive. Collapsible via toggle.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { ChevronRight, Terminal } from 'lucide-react';
import type { LogEntry } from '@/types/orchestration';

interface LogConsoleProps {
  entries: LogEntry[];
}

const LEVEL_COLOR: Record<LogEntry['level'], string> = {
  info: 'text-brand-electric',
  success: 'text-emerald-400',
  error: 'text-red-400',
};

export default function LogConsole({ entries }: LogConsoleProps) {
  const [collapsed, setCollapsed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries.length]);

  return (
    <div className="glass-card overflow-hidden flex flex-col">
      {/* Header */}
      <button
        onClick={() => setCollapsed((s) => !s)}
        className="flex items-center gap-2 px-4 py-3 text-left w-full hover:bg-white/5 transition-colors"
      >
        <ChevronRight
          className={`w-4 h-4 text-brand-silver/60 transition-transform duration-200 ${
            collapsed ? '' : 'rotate-90'
          }`}
        />
        <Terminal className="w-4 h-4 text-brand-silver/60" />
        <span className="text-sm font-heading font-semibold text-white flex-1">
          Execution Log
        </span>
        <span className="text-xs text-brand-silver/40">
          {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
        </span>
      </button>

      {/* Log body */}
      {!collapsed && (
        <div
          ref={scrollRef}
          className="bg-brand-midnight/60 px-4 py-3 font-mono text-xs overflow-y-auto max-h-[300px] space-y-0.5"
        >
          {entries.length === 0 ? (
            <p className="text-brand-silver/40 italic">
              Waiting for pipeline events&hellip;
            </p>
          ) : (
            entries.map((entry, idx) => (
              <div key={idx} className="flex gap-2 leading-5">
                <span className="text-brand-silver/40 shrink-0">
                  [{entry.timestamp}]
                </span>
                <span className={`${LEVEL_COLOR[entry.level]} shrink-0`}>
                  {humanLabel(entry.nodeId)}:
                </span>
                <span className="text-brand-silver/80">
                  {entry.message}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function humanLabel(nodeId: string): string {
  return nodeId
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
