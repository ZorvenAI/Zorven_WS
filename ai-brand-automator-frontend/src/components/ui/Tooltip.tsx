'use client';

interface TooltipProps {
  text: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * Inline hover/focus tooltip.
 * Wraps children in a group container and shows tooltip above on hover or focus.
 */
export default function Tooltip({ text, children, className = '' }: TooltipProps) {
  return (
    <span className={`group/tip relative inline-flex ${className}`} tabIndex={0}>
      {children}
      <span
        role="tooltip"
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 px-3 py-2 rounded-lg bg-brand-midnight border border-white/10 shadow-lg text-xs text-brand-silver leading-relaxed opacity-0 pointer-events-none group-hover/tip:opacity-100 group-focus-within/tip:opacity-100 transition-opacity duration-200 z-50"
      >
        {text}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-white/10" />
      </span>
    </span>
  );
}
