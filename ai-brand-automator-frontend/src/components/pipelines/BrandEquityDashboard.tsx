/**
 * BrandEquityDashboard — Specialized result view for ISO Brand Equity
 * analysis pipelines.
 *
 * Renders:
 *   - Radial gauge meters for each equity pillar (Awareness, Sentiment, Financials)
 *   - Central brand equity score
 *   - NPV valuation bar and 5-year forecast chart (when valuation data present)
 *   - BSI pillar radar chart (when pillar data present)
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
  Loader2,
  BookmarkPlus,
  BookmarkCheck,
  AlertCircle,
} from 'lucide-react';
import { apiClient } from '@/lib/api';
import { formatCompact, formatPercent } from '@/lib/utils/iso-formatters';
import NpvChart from '@/components/dashboard/npv-chart';
import PillarRadar from '@/components/dashboard/pillar-radar';

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
  const [ragSaveState, setRagSaveState] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');

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

  // ISO 10668 valuation data (from intelligence-agent-svc via ManagerNode)
  const valuation = resultData.valuation as
    | {
        brand_value_npv?: number;
        royalty_rate?: number;
        discount_rate?: number;
        tax_rate?: number;
        horizon_years?: number;
        annual_royalties?: number[];
        methodology?: string;
      }
    | undefined;

  // BSI pillar data for radar chart — extracted from node_results
  const nodeResults = resultData.node_results as Record<string, Record<string, unknown>> | undefined;
  const bsiPillars: { name: string; score: number; weight?: number }[] = [];
  if (nodeResults) {
    for (const output of Object.values(nodeResults)) {
      const bsi = output?.bsi as { pillars?: { name: string; score: number; weight?: number }[] } | undefined;
      if (bsi?.pillars && bsi.pillars.length > 0) {
        bsiPillars.push(...bsi.pillars);
        break;
      }
    }
  }

  const hasValuation = valuation && typeof valuation.brand_value_npv === 'number';
  const hasAnnualRoyalties = valuation?.annual_royalties && valuation.annual_royalties.length > 0;
  const hasRadarData = bsiPillars.length >= 3;

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

  /** Build a human-readable report from the brand equity data. */
  const buildReport = (): string => {
    const lines: string[] = [];

    if (score !== null) {
      lines.push(`Brand Equity Score: ${Math.round(score)} / 100`);
      lines.push('');
    }

    if (hasPillars) {
      lines.push('Pillar Scores:');
      if (awareness !== null) lines.push(`  Awareness: ${Math.round(awareness)} / 100`);
      if (sentiment !== null) lines.push(`  Sentiment: ${Math.round(sentiment)} / 100`);
      if (financials !== null) lines.push(`  Financials: ${Math.round(financials)} / 100`);
      lines.push('');
    }

    if (hasValuation) {
      lines.push('Brand Valuation:');
      lines.push(`  NPV: ${formatCompact(valuation!.brand_value_npv!)}`);
      if (valuation!.royalty_rate != null)
        lines.push(`  Royalty Rate: ${formatPercent(valuation!.royalty_rate)}`);
      if (valuation!.discount_rate != null)
        lines.push(`  Discount Rate (WACC): ${formatPercent(valuation!.discount_rate)}`);
      if (valuation!.horizon_years != null)
        lines.push(`  Horizon: ${valuation!.horizon_years} years`);
      if (valuation!.methodology)
        lines.push(`  Methodology: ${valuation!.methodology.replace(/_/g, ' ')}`);
      lines.push('');
    }

    if (summary) {
      lines.push('Summary:');
      lines.push(summary);
      lines.push('');
    }

    if (findings && findings.length > 0) {
      lines.push('Key Findings:');
      findings.forEach((f, i) => lines.push(`  ${i + 1}. ${f}`));
      lines.push('');
    }

    if (recommendations && recommendations.length > 0) {
      lines.push('Recommendations:');
      recommendations.forEach((r, i) => lines.push(`  ${i + 1}. ${r}`));
      lines.push('');
    }

    if (sources && sources.length > 0) {
      lines.push('Sources:');
      sources.forEach((src) => {
        const label = src.title ?? src.url ?? 'Unknown source';
        lines.push(`  - ${label}${src.url ? ` (${src.url})` : ''}`);
      });
      lines.push('');
    }

    return lines.join('\n');
  };

  const handleSaveToRAG = async () => {
    if (ragSaveState === 'saving') return;
    setRagSaveState('saving');

    try {
      const resp = await apiClient.post('/ai/chat/save-to-rag/', {
        content: buildReport(),
        title: 'Brand Equity Analysis',
      });
      setRagSaveState(resp.ok ? 'saved' : 'error');
    } catch {
      setRagSaveState('error');
    }
    setTimeout(() => setRagSaveState('idle'), 3000);
  };

  return (
    <div className="glass-card p-6 space-y-8">
      {/* Header + actions */}
      <div className="flex items-center justify-between">
        <h3 className="font-heading text-sm font-heading font-semibold text-white">
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
          <button
            onClick={handleSaveToRAG}
            disabled={ragSaveState === 'saving' || ragSaveState === 'saved'}
            className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5 disabled:opacity-60"
          >
            {ragSaveState === 'saving' && (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            )}
            {ragSaveState === 'saved' && (
              <BookmarkCheck className="w-3.5 h-3.5 text-emerald-400" />
            )}
            {ragSaveState === 'error' && (
              <AlertCircle className="w-3.5 h-3.5 text-red-400" />
            )}
            {ragSaveState === 'idle' && (
              <BookmarkPlus className="w-3.5 h-3.5" />
            )}
            {ragSaveState === 'saved'
              ? 'Saved'
              : ragSaveState === 'error'
                ? 'Failed'
                : 'Save to RAG'}
          </button>
        </div>
      </div>

      {/* NPV Valuation bar */}
      {hasValuation && (
        <div className="flex items-center justify-between rounded-lg bg-white/5 px-5 py-3">
          <div>
            <span className="text-xs font-medium text-brand-silver/50 uppercase tracking-widest">
              Brand Valuation (NPV)
            </span>
            <p className="text-xl font-heading font-bold text-white">
              {formatCompact(valuation.brand_value_npv!)}
            </p>
          </div>
          <div className="flex gap-6 text-right">
            {valuation.royalty_rate != null && (
              <div>
                <span className="text-[10px] text-brand-silver/40 uppercase">Royalty</span>
                <p className="text-sm font-medium text-brand-silver">
                  {formatPercent(valuation.royalty_rate)}
                </p>
              </div>
            )}
            {valuation.discount_rate != null && (
              <div>
                <span className="text-[10px] text-brand-silver/40 uppercase">WACC</span>
                <p className="text-sm font-medium text-brand-silver">
                  {formatPercent(valuation.discount_rate)}
                </p>
              </div>
            )}
            {valuation.horizon_years != null && (
              <div>
                <span className="text-[10px] text-brand-silver/40 uppercase">Horizon</span>
                <p className="text-sm font-medium text-brand-silver">
                  {valuation.horizon_years}yr
                </p>
              </div>
            )}
            {valuation.methodology && (
              <div>
                <span className="text-[10px] text-brand-silver/40 uppercase">Method</span>
                <p className="text-sm font-medium text-brand-silver capitalize">
                  {valuation.methodology.replace('_', ' ')}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

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

      {/* Charts row: NPV forecast + BSI radar */}
      {(hasAnnualRoyalties || hasRadarData) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 py-2">
          {hasAnnualRoyalties && (
            <div className="flex flex-col items-center">
              <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
                5-Year Royalty Relief Forecast
              </h4>
              <NpvChart
                annualRoyalties={valuation!.annual_royalties!}
                totalNpv={valuation!.brand_value_npv}
              />
            </div>
          )}
          {hasRadarData && (
            <div className="flex flex-col items-center">
              <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
                BSI Pillar Comparison
              </h4>
              <PillarRadar pillars={bsiPillars} />
            </div>
          )}
        </div>
      )}

      {/* Summary */}
      {summary && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Summary
          </h4>
          <p className="text-sm text-brand-silver leading-relaxed">{summary}</p>
        </section>
      )}

      {/* Key findings */}
      {findings && findings.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
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
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
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
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
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
