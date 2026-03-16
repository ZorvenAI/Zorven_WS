/**
 * NpvChart — Pure SVG area chart for the 5-year Royalty Relief NPV forecast.
 *
 * Renders annual post-tax royalty values as a filled area chart with
 * data-point circles, axis labels, and an optional total NPV annotation.
 */

'use client';

import { formatCurrency, formatCompact } from '@/lib/utils/iso-formatters';

interface NpvChartProps {
  /** Post-tax annual royalty values (one per year). */
  annualRoyalties: number[];
  /** Total NPV (sum of discounted royalties). */
  totalNpv?: number;
  /** Chart width in px. */
  width?: number;
  /** Chart height in px. */
  height?: number;
}

const PAD = { top: 24, right: 16, bottom: 32, left: 56 };

export default function NpvChart({
  annualRoyalties,
  totalNpv,
  width = 420,
  height = 220,
}: NpvChartProps) {
  if (annualRoyalties.length === 0) return null;

  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  const maxVal = Math.max(...annualRoyalties, 1);
  const minVal = 0;
  const range = maxVal - minVal || 1;

  const points = annualRoyalties.map((v, i) => {
    const x = PAD.left + (i / Math.max(annualRoyalties.length - 1, 1)) * plotW;
    const y = PAD.top + plotH - ((v - minVal) / range) * plotH;
    return { x, y, value: v };
  });

  // SVG path for the area fill
  const lineD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  const areaD = `${lineD} L${points[points.length - 1].x},${PAD.top + plotH} L${points[0].x},${PAD.top + plotH} Z`;

  // Y-axis ticks (4 ticks)
  const yTicks = Array.from({ length: 4 }, (_, i) => {
    const val = minVal + (range * (3 - i)) / 3;
    const y = PAD.top + (i / 3) * plotH;
    return { val, y };
  });

  return (
    <div className="flex flex-col items-center gap-2">
      {totalNpv !== undefined && (
        <div className="text-center mb-1">
          <span className="text-xs font-medium text-brand-silver/50 uppercase tracking-widest">
            Total NPV
          </span>
          <p className="text-lg font-heading font-bold text-white">
            {formatCompact(totalNpv)}
          </p>
        </div>
      )}

      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="overflow-visible"
      >
        <defs>
          <linearGradient id="npv-area-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fad55c" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#fad55c" stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {/* Grid lines + Y labels */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={PAD.left}
              y1={t.y}
              x2={width - PAD.right}
              y2={t.y}
              stroke="rgba(225,225,230,0.06)"
              strokeDasharray="4 4"
            />
            <text
              x={PAD.left - 8}
              y={t.y + 4}
              textAnchor="end"
              className="fill-brand-silver/40"
              fontSize="9"
            >
              {formatCompact(t.val)}
            </text>
          </g>
        ))}

        {/* Area fill */}
        <path d={areaD} fill="url(#npv-area-grad)" />

        {/* Line */}
        <path
          d={lineD}
          fill="none"
          stroke="#fad55c"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* Data points */}
        {points.map((p, i) => (
          <g key={i}>
            <circle
              cx={p.x}
              cy={p.y}
              r="4"
              fill="var(--brand-midnight)"
              stroke="#fad55c"
              strokeWidth="2"
            />
            {/* Tooltip text */}
            <text
              x={p.x}
              y={p.y - 10}
              textAnchor="middle"
              className="fill-brand-silver/60"
              fontSize="8"
            >
              {formatCurrency(p.value)}
            </text>
          </g>
        ))}

        {/* X-axis labels (Year 1, Year 2, …) */}
        {points.map((p, i) => (
          <text
            key={i}
            x={p.x}
            y={height - 6}
            textAnchor="middle"
            className="fill-brand-silver/50"
            fontSize="9"
          >
            Yr {i + 1}
          </text>
        ))}
      </svg>
    </div>
  );
}
