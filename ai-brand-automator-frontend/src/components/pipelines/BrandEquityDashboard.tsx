/**
 * BrandEquityDashboard — Specialized result view for ISO Brand Equity
 * analysis pipelines.
 *
 * Renders:
 *   - Radial gauge meters for each equity pillar (Awareness, Sentiment, Financials)
 *   - Central brand equity score
 *   - Grounding citations with source links
 *   - Structured findings & recommendations
 *
 * All gauges use pure SVG — no charting library required.
 */

'use client';

import { useState } from 'react';
import {
  ClipboardCopy,
  Download,
  Check,
  FileText,
  Globe,
  DollarSign,
} from 'lucide-react';

interface BrandEquityDashboardProps {
  resultData: Record<string, unknown>;
}

// ── Radial Gauge (pure SVG) ──

interface GaugeProps {
  label: string;
  score: number;
  maxScore?: number;
  color?: string;
}

function RadialGauge({
  label,
  score,
  maxScore = 100,
  color = '#00F5FF',
}: GaugeProps) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(score / maxScore, 1);
  const offset = circumference * (1 - pct);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="100" height="100" viewBox="0 0 100 100">
        {/* Background ring */}
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="rgba(225,225,230,0.1)"
          strokeWidth="6"
        />
        {/* Filled arc */}
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 50 50)"
          className="transition-all duration-700 ease-out"
        />
        {/* Score text */}
        <text
          x="50"
          y="48"
          textAnchor="middle"
          className="fill-brand-silver font-heading"
          fontSize="18"
          fontWeight="bold"
        >
          {Math.round(score)}
        </text>
        <text
          x="50"
          y="62"
          textAnchor="middle"
          className="fill-brand-silver/50"
          fontSize="9"
        >
          / {maxScore}
        </text>
      </svg>
      <span className="text-xs font-medium text-brand-silver/70 uppercase tracking-wider">
        {label}
      </span>
    </div>
  );
}

// ── Source citation icon ──

const SOURCE_ICON: Record<string, React.ReactNode> = {
  document: <FileText className="w-3.5 h-3.5" />,
  web: <Globe className="w-3.5 h-3.5" />,
  financial: <DollarSign className="w-3.5 h-3.5" />,
};

// ── Main ──

export default function BrandEquityDashboard({
  resultData,
}: BrandEquityDashboardProps) {
  const [copied, setCopied] = useState(false);

  // Extract well-known brand equity keys
  const score = (resultData.score as number) ?? null;
  const awareness = (resultData.awareness as number) ?? null;
  const sentiment = (resultData.sentiment as number) ?? null;
  const financials = (resultData.financials as number) ?? null;
  const summary = resultData.summary as string | undefined;
  const findings = resultData.findings as string[] | undefined;
  const recommendations = resultData.recommendations as string[] | undefined;
  const sources = resultData.sources as
    | { type?: string; title?: string; url?: string }[]
    | undefined;

  const hasPillars =
    awareness !== null || sentiment !== null || financials !== null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(resultData, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard not available
    }
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(resultData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'brand-equity-results.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="glass-card p-6 space-y-8">
      {/* Header + actions */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-heading font-semibold text-white">
          Brand Equity Analysis
        </h3>
        <div className="flex gap-2">
          <button
            onClick={handleCopy}
            className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <ClipboardCopy className="w-3.5 h-3.5" />
            )}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            onClick={handleExport}
            className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            Export
          </button>
        </div>
      </div>

      {/* Central score */}
      {score !== null && (
        <div className="flex flex-col items-center py-2">
          <span className="text-xs font-medium text-brand-silver/50 uppercase tracking-widest mb-2">
            Brand Equity Score
          </span>
          <div className="relative">
            <svg width="140" height="140" viewBox="0 0 140 140">
              <circle
                cx="70"
                cy="70"
                r="58"
                fill="none"
                stroke="rgba(225,225,230,0.08)"
                strokeWidth="8"
              />
              <circle
                cx="70"
                cy="70"
                r="58"
                fill="none"
                stroke="url(#equity-gradient)"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={2 * Math.PI * 58}
                strokeDashoffset={
                  2 * Math.PI * 58 * (1 - Math.min(score / 100, 1))
                }
                transform="rotate(-90 70 70)"
                className="transition-all duration-1000 ease-out"
              />
              <defs>
                <linearGradient
                  id="equity-gradient"
                  x1="0%"
                  y1="0%"
                  x2="100%"
                  y2="100%"
                >
                  <stop offset="0%" stopColor="#00F5FF" />
                  <stop offset="100%" stopColor="#14b8a6" />
                </linearGradient>
              </defs>
              <text
                x="70"
                y="66"
                textAnchor="middle"
                className="fill-white font-heading"
                fontSize="28"
                fontWeight="bold"
              >
                {Math.round(score)}
              </text>
              <text
                x="70"
                y="84"
                textAnchor="middle"
                className="fill-brand-silver/50"
                fontSize="11"
              >
                / 100
              </text>
            </svg>
          </div>
        </div>
      )}

      {/* Pillar gauges */}
      {hasPillars && (
        <div className="flex justify-center gap-10 py-2">
          {awareness !== null && (
            <RadialGauge label="Awareness" score={awareness} color="#00F5FF" />
          )}
          {sentiment !== null && (
            <RadialGauge label="Sentiment" score={sentiment} color="#8b5cf6" />
          )}
          {financials !== null && (
            <RadialGauge label="Financials" score={financials} color="#14b8a6" />
          )}
        </div>
      )}

      {/* Summary */}
      {summary && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Summary
          </h4>
          <p className="text-sm text-brand-silver leading-relaxed">{summary}</p>
        </section>
      )}

      {/* Key findings */}
      {findings && findings.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Key Findings
          </h4>
          <ul className="list-disc list-inside space-y-1">
            {findings.map((f, i) => (
              <li key={i} className="text-sm text-brand-silver">
                {f}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Recommendations */}
      {recommendations && recommendations.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Recommendations
          </h4>
          <ol className="list-decimal list-inside space-y-1">
            {recommendations.map((r, i) => (
              <li key={i} className="text-sm text-brand-silver">
                {r}
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Grounding citations */}
      {sources && sources.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Sources
          </h4>
          <div className="space-y-1.5">
            {sources.map((src, i) => (
              <div
                key={i}
                className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2"
              >
                <span className="text-brand-silver/50">
                  {SOURCE_ICON[src.type ?? 'document'] ?? SOURCE_ICON.document}
                </span>
                {src.url ? (
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-brand-electric hover:underline truncate"
                  >
                    {src.title ?? src.url}
                  </a>
                ) : (
                  <span className="text-sm text-brand-silver truncate">
                    {src.title ?? 'Unknown source'}
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
