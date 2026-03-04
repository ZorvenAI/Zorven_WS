/**
 * PillarRadar — Pure SVG radar chart for BSI pillar comparison.
 *
 * Renders a 3-axis (or N-axis) radar chart showing pillar scores
 * with labeled vertices and a filled polygon overlay.
 */

'use client';

interface PillarData {
  name: string;
  score: number;
  weight?: number;
}

interface PillarRadarProps {
  pillars: PillarData[];
  /** Max score for the axes. */
  maxScore?: number;
  /** Chart size in px (square). */
  size?: number;
}

const COLORS = ['#00F5FF', '#8b5cf6', '#14b8a6', '#f59e0b', '#ef4444'];

export default function PillarRadar({
  pillars,
  maxScore = 100,
  size = 220,
}: PillarRadarProps) {
  if (pillars.length < 3) return null;

  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 36;
  const n = pillars.length;

  /** Angle for the i-th axis (starting from top, going clockwise). */
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;

  /** Point on an axis at a given fraction (0-1) of the radius. */
  const axisPoint = (i: number, frac: number) => ({
    x: cx + radius * frac * Math.cos(angle(i)),
    y: cy + radius * frac * Math.sin(angle(i)),
  });

  // Concentric grid rings
  const rings = [0.25, 0.5, 0.75, 1.0];

  // Data polygon points
  const dataPoints = pillars.map((p, i) =>
    axisPoint(i, Math.min(p.score / maxScore, 1)),
  );
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + ' Z';

  return (
    <div className="flex flex-col items-center gap-2">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="overflow-visible"
      >
        {/* Grid rings */}
        {rings.map((r) => {
          const pts = Array.from({ length: n }, (_, i) => axisPoint(i, r));
          const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + ' Z';
          return (
            <path
              key={r}
              d={d}
              fill="none"
              stroke="rgba(225,225,230,0.08)"
              strokeWidth="1"
            />
          );
        })}

        {/* Axis spokes */}
        {Array.from({ length: n }, (_, i) => {
          const end = axisPoint(i, 1);
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={end.x}
              y2={end.y}
              stroke="rgba(225,225,230,0.1)"
              strokeWidth="1"
            />
          );
        })}

        {/* Filled data polygon */}
        <path d={dataPath} fill="#00F5FF" fillOpacity={0.15} />
        <path
          d={dataPath}
          fill="none"
          stroke="#00F5FF"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* Data point dots */}
        {dataPoints.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r="4"
            fill="var(--brand-midnight)"
            stroke={COLORS[i % COLORS.length]}
            strokeWidth="2"
          />
        ))}

        {/* Axis labels */}
        {pillars.map((pillar, i) => {
          const label = axisPoint(i, 1.22);
          return (
            <text
              key={i}
              x={label.x}
              y={label.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-brand-silver/70"
              fontSize="10"
              fontWeight="500"
            >
              {pillar.name}
            </text>
          );
        })}

        {/* Score values next to data points */}
        {pillars.map((pillar, i) => {
          const scorePos = axisPoint(i, Math.min(pillar.score / maxScore, 1) + 0.14);
          return (
            <text
              key={`score-${i}`}
              x={scorePos.x}
              y={scorePos.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-brand-silver/50"
              fontSize="9"
            >
              {Math.round(pillar.score)}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
