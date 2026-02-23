'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Brain } from 'lucide-react';

interface ThinkingBubbleProps {
  thinking: string;
}

export function ThinkingBubble({ thinking }: ThinkingBubbleProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!thinking) return null;

  return (
    <div className="mb-2">
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="flex items-center gap-1.5 text-[11px] text-brand-silver/40 hover:text-brand-silver/60 transition-colors"
      >
        <Brain className="w-3 h-3" />
        {isOpen ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        {isOpen ? 'Hide thinking' : 'Show thinking'}
      </button>
      {isOpen && (
        <div className="mt-1.5 px-3 py-2 rounded-lg bg-white/[0.02] border border-white/5 text-xs text-brand-silver/40 italic leading-relaxed whitespace-pre-wrap">
          {thinking}
        </div>
      )}
    </div>
  );
}
