'use client';

interface TooltipProps {
  text: string;
  children: React.ReactNode;
  className?: string;
  tabIndex?: number;
}

/**
 * Inline hover/focus tooltip.
 * Wraps children in a group container and shows tooltip above on hover or focus.
 * Pass tabIndex={0} for non-focusable children (text, spans). Omit for
 * focusable children (buttons, links) to avoid double tab stops.
 */
export default function Tooltip({
  text,
  children,
  className = '',
  tabIndex,
}: TooltipProps) {
  return (
    <div className={`group/tip relative inline-flex ${className}`} tabIndex={tabIndex}>
      {children}
      <div
        role="tooltip"
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 px-3 py-2 rounded-lg bg-brand-midnight border border-white/10 shadow-lg text-xs text-brand-silver leading-relaxed opacity-0 pointer-events-none group-hover/tip:opacity-100 group-focus-within/tip:opacity-100 transition-opacity duration-200 z-50"
      >
        {text}
        <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-white/10" />
      </div>
    </div>
  );
}
