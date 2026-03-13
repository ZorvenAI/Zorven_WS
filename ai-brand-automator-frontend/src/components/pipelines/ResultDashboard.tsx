/**
 * ResultDashboard — renders the final result_data from a completed
 * analysis job as structured sections: summary, findings,
 * recommendations, blog post (rendered markdown with copy/export),
 * and social promotion status.
 *
 * Technical keys like node_results, awareness, sentiment, financials,
 * and valuation are suppressed — meaningful data is extracted and
 * presented in user-friendly sections instead.
 */

'use client';

import { useState } from 'react';
import {
  ClipboardCopy,
  Download,
  Check,
  ExternalLink,
  Loader2,
  BookmarkPlus,
  BookmarkCheck,
  AlertCircle,
} from 'lucide-react';
import { apiClient } from '@/lib/api';
import BrandEquityDashboard from './BrandEquityDashboard';
import { MarkdownMessage } from '@/components/chat/MarkdownMessage';

interface ResultDashboardProps {
  resultData: Record<string, unknown>;
  /** Optional manifest name — used to route to specialized dashboards. */
  manifestName?: string | null;
}

interface PublishResultEntry {
  platform: string;
  status: string;
  post_url?: string;
  post_id?: string;
  error?: string;
  scheduled_date?: string;
}

/* ── DataToolbar — reusable Copy / Export / Save-to-RAG for any block ── */

type DataFormat = 'json' | 'csv' | 'text' | 'markdown';

interface DataToolbarProps {
  content: string;
  title?: string;
  format?: DataFormat;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-+$/, '')
    .replace(/^-+/, '');
}

/** Convert markdown to clean readable text for RAG storage. */
function markdownToPlainText(md: string): string {
  return md
    .replace(/^#{1,6}\s+(.+)$/gm, '$1')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/_(.+?)_/g, '$1')
    .replace(/`{3}[\s\S]*?`{3}/g, (m) =>
      m.replace(/^`{3}\w*\n?/gm, '').replace(/`{3}$/gm, ''))
    .replace(/`(.+?)`/g, '$1')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1 ($2)')
    .replace(/^>\s?/gm, '')
    .replace(/^[-*+]\s+/gm, '- ')
    .replace(/^---+$/gm, '')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function DataToolbar({ content, title, format = 'text' }: DataToolbarProps) {
  const [copied, setCopied] = useState(false);
  const [ragSaveState, setRagSaveState] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');

  const copyLabel =
    format === 'json' ? 'Copy JSON' : format === 'csv' ? 'Copy CSV' : 'Copy';
  const ext =
    format === 'json'
      ? '.json'
      : format === 'csv'
        ? '.csv'
        : format === 'markdown'
          ? '.md'
          : '.txt';
  const mime =
    format === 'json'
      ? 'application/json'
      : format === 'csv'
        ? 'text/csv'
        : format === 'markdown'
          ? 'text/markdown'
          : 'text/plain';

  const deriveFilename = (): string => {
    if (format === 'markdown') {
      for (const line of content.split('\n')) {
        if (line.startsWith('# ')) {
          return slugify(line.replace(/^#\s+/, '').trim()) + ext;
        }
      }
    }
    return slugify(title ?? 'export') + ext;
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard not available
    }
  };

  const handleExport = () => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = deriveFilename();
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSaveToRAG = async () => {
    if (ragSaveState === 'saving') return;
    setRagSaveState('saving');
    const ragTitle = title ?? 'Export';
    const ragContent =
      format === 'markdown' ? markdownToPlainText(content) : content;
    try {
      const resp = await apiClient.post('/ai/chat/save-to-rag/', {
        content: ragContent,
        title: ragTitle,
      });
      setRagSaveState(resp.ok ? 'saved' : 'error');
    } catch {
      setRagSaveState('error');
    }
    setTimeout(() => setRagSaveState('idle'), 3000);
  };

  return (
    <div className="flex gap-2 mb-2">
      <button
        onClick={handleCopy}
        className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5"
      >
        {copied ? (
          <Check className="w-3.5 h-3.5 text-emerald-400" />
        ) : (
          <ClipboardCopy className="w-3.5 h-3.5" />
        )}
        {copied ? 'Copied' : copyLabel}
      </button>
      <button
        onClick={handleExport}
        className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5"
      >
        <Download className="w-3.5 h-3.5" />
        Export {ext}
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
  );
}

function renderValue(value: unknown): React.ReactNode {
  if (typeof value === 'string') return <MarkdownMessage content={value} />;
  if (typeof value === 'number' || typeof value === 'boolean')
    return <p className="text-sm text-brand-silver">{String(value)}</p>;
  if (Array.isArray(value)) {
    return (
      <div className="space-y-2">
        {value.map((item, i) => (
          <div key={i}>
            {typeof item === 'string' ? (
              <MarkdownMessage content={item} />
            ) : (
              <pre className="text-xs text-brand-silver/80 bg-white/5 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(item, null, 2)}
              </pre>
            )}
          </div>
        ))}
      </div>
    );
  }
  if (value && typeof value === 'object') {
    return (
      <pre className="text-xs text-brand-silver/80 bg-white/5 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  return null;
}

/** Convert resultData into human-readable plain text for copy/export. */
function resultDataToText(data: Record<string, unknown>): string {
  const lines: string[] = [];

  const summary = data.summary as string | undefined;
  if (summary) {
    lines.push(summary, '');
  }

  // Market research sections
  const overview = data.market_overview as string | undefined;
  if (overview) {
    lines.push('MARKET OVERVIEW', '-'.repeat(40), overview, '');
  }

  const sizing = data.market_sizing as Record<string, unknown> | undefined;
  if (sizing) {
    lines.push('MARKET SIZING', '-'.repeat(40));
    for (const key of ['tam', 'sam', 'som']) {
      const entry = sizing[key];
      if (entry && typeof entry === 'object') {
        const obj = entry as Record<string, unknown>;
        const label = key.toUpperCase();
        lines.push(`${label}: ${obj.value ?? '-'}`);
        if (obj.description) lines.push(`  ${obj.description}`);
      } else if (typeof entry === 'string') {
        lines.push(`${key.toUpperCase()}: ${entry}`);
      }
    }
    lines.push('');
  }

  const competitors = data.competitive_landscape as Array<Record<string, unknown>> | undefined;
  if (competitors && competitors.length > 0) {
    lines.push(`COMPETITIVE LANDSCAPE (${competitors.length})`, '-'.repeat(40));
    for (const c of competitors) {
      lines.push(`- ${c.name ?? '-'}${c.market_position ? ` -- ${c.market_position}` : ''}`);
      if (c.description) lines.push(`  ${c.description}`);
    }
    lines.push('');
  }

  const trends = data.industry_trends as string[] | undefined;
  if (trends && trends.length > 0) {
    lines.push('INDUSTRY TRENDS', '-'.repeat(40));
    trends.forEach((t, i) => lines.push(`${i + 1}. ${t}`));
    lines.push('');
  }

  const findings = data.findings as string[] | undefined;
  if (findings && findings.length > 0) {
    lines.push('KEY FINDINGS', '-'.repeat(40));
    findings.forEach((f) => lines.push(`- ${f}`));
    lines.push('');
  }

  const recommendations = data.recommendations as string[] | undefined;
  if (recommendations && recommendations.length > 0) {
    lines.push('RECOMMENDATIONS', '-'.repeat(40));
    recommendations.forEach((r, i) => lines.push(`${i + 1}. ${r}`));
    lines.push('');
  }

  const sources = data.sources as Array<Record<string, unknown>> | undefined;
  if (sources && sources.length > 0) {
    lines.push(`SOURCES (${sources.length})`, '-'.repeat(40));
    for (const s of sources) {
      const title = s.title ?? s.url ?? '-';
      const url = s.url ? ` -- ${s.url}` : '';
      lines.push(`- ${title}${url}`);
    }
    lines.push('');
  }

  // If no structured sections beyond a possible summary were added,
  // fall back to generic extraction. push(summary, '') adds 2 items.
  if (lines.length <= 2) {
    const skip = new Set(['node_results', 'ui_schema', 'score', 'awareness', 'sentiment', 'financials', 'valuation', 'market_overview', 'market_sizing', 'competitive_landscape', 'industry_trends', 'economic_indicators', 'sources', 'confidence_score', 'methodology_notes']);
    for (const [key, val] of Object.entries(data)) {
      if (skip.has(key)) continue;
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      if (typeof val === 'string') {
        lines.push(`${label}`, val, '');
      } else if (Array.isArray(val)) {
        lines.push(label);
        val.forEach((item) => lines.push(`- ${typeof item === 'string' ? item : JSON.stringify(item)}`));
        lines.push('');
      }
    }
  }

  return lines.join('\n').trim();
}

function formatCompactNumber(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return n.toLocaleString();
}

function sectionTitle(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatScheduledDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

/* ── Market Research Types ─────────────────────────────────────────── */

interface MarketSizingEntry {
  value: string;
  description?: string;
  methodology?: string;
}

interface CompetitorEntry {
  name: string;
  description?: string;
  market_position?: string;
  strengths?: string[];
  weaknesses?: string[];
}

interface SourceEntry {
  type?: string;
  title?: string;
  url?: string;
  description?: string;
}

/* ── Competitor Intelligence Types ─────────────────────────────────── */

interface CIACompetitorProfile {
  slug?: string;
  name: string;
  website?: string;
  description?: string;
  market_position?: string;
  confidence?: number;
  website_profile?: Record<string, unknown>;
  social_presence?: Record<string, unknown>;
  review_profile?: Record<string, unknown>;
  pricing_profile?: Record<string, unknown>;
  market_share_estimate?: Record<string, unknown>;
  swot?: Record<string, unknown>;
}

interface SWOTAnalysis {
  competitor: string;
  strengths?: string[];
  weaknesses?: string[];
  opportunities?: string[];
  threats?: string[];
}

interface PositioningGap {
  dimension: string;
  gap_description?: string;
  opportunity_score?: number;
  evidence?: string;
}

interface BenchmarkRanking {
  competitor: string;
  overall_score?: number;
  tier?: string;
}

/* ── MarketResearchDashboard (inline) ─────────────────────────────── */

function MarketResearchSection({
  marketOverview,
  marketSizing,
  competitiveLandscape,
  industryTrends,
  economicIndicators,
  sources,
  confidenceScore,
  findings,
  recommendations,
}: {
  marketOverview?: string;
  marketSizing?: Record<string, unknown>;
  competitiveLandscape?: CompetitorEntry[];
  industryTrends?: string[];
  economicIndicators?: Record<string, unknown>;
  sources?: SourceEntry[];
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  // Extract TAM/SAM/SOM from market_sizing
  const sizingEntries: Array<{ label: string; data: MarketSizingEntry }> = [];
  if (marketSizing) {
    for (const key of ['tam', 'sam', 'som']) {
      const entry = marketSizing[key];
      if (entry && typeof entry === 'object') {
        const label =
          key === 'tam'
            ? 'Total Addressable Market (TAM)'
            : key === 'sam'
              ? 'Serviceable Addressable Market (SAM)'
              : 'Serviceable Obtainable Market (SOM)';
        sizingEntries.push({ label, data: entry as MarketSizingEntry });
      } else if (typeof entry === 'string') {
        const label =
          key === 'tam' ? 'TAM' : key === 'sam' ? 'SAM' : 'SOM';
        sizingEntries.push({ label, data: { value: entry } });
      }
    }
  }

  // Parse economic indicator entries
  const econEntries: Array<{ name: string; value: string; date?: string }> = [];
  if (economicIndicators && typeof economicIndicators === 'object') {
    for (const [key, val] of Object.entries(economicIndicators)) {
      if (val && typeof val === 'object') {
        const obj = val as Record<string, unknown>;
        const latestValue = obj.latest_value ?? obj.value;
        const latestDate = obj.latest_date ?? obj.date;
        if (latestValue != null) {
          econEntries.push({
            name: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
            value: typeof latestValue === 'number'
              ? formatCompactNumber(latestValue)
              : String(latestValue),
            date: latestDate ? String(latestDate) : undefined,
          });
        }
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Confidence badge */}
      {confidenceScore != null && confidenceScore > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
            Confidence
          </span>
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold ${
              confidenceScore >= 0.7
                ? 'bg-emerald-500/20 text-emerald-400'
                : confidenceScore >= 0.4
                  ? 'bg-amber-500/20 text-amber-400'
                  : 'bg-red-500/20 text-red-400'
            }`}
          >
            {Math.round(confidenceScore * 100)}%
          </span>
        </div>
      )}

      {/* Market Overview */}
      {marketOverview && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Market Overview
          </h4>
          <div className="bg-white/5 rounded-lg p-4 border border-white/10">
            <MarkdownMessage content={marketOverview} />
          </div>
        </section>
      )}

      {/* TAM / SAM / SOM Cards */}
      {sizingEntries.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Market Sizing
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {sizingEntries.map(({ label, data }, i) => (
              <div
                key={i}
                className="glass-card p-4 rounded-lg border border-white/10"
              >
                <p className="text-xs text-brand-silver/60 mb-1">{label}</p>
                <p className="text-sm font-medium text-brand-electric">
                  {data.value}
                </p>
                {data.description && (
                  <p className="text-xs text-brand-silver/70 mt-2 line-clamp-3">
                    {data.description}
                  </p>
                )}
                {data.methodology && (
                  <p className="text-xs text-brand-silver/50 mt-1 italic">
                    {data.methodology}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Competitive Landscape */}
      {competitiveLandscape && competitiveLandscape.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Competitive Landscape ({competitiveLandscape.length})
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {competitiveLandscape.map((comp, i) => (
              <div
                key={i}
                className="bg-white/5 rounded-lg p-4 border border-white/10"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h5 className="text-sm font-semibold text-white">
                    {comp.name}
                  </h5>
                </div>
                {comp.market_position && (
                  <p className="text-xs text-brand-silver/80 mb-2 line-clamp-2">
                    {comp.market_position}
                  </p>
                )}
                {comp.description && (
                  <p className="text-xs text-brand-silver/60 line-clamp-3">
                    {comp.description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Industry Trends */}
      {industryTrends && industryTrends.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Industry Trends
          </h4>
          <div className="space-y-2">
            {industryTrends.map((trend, i) => (
              <div
                key={i}
                className="flex items-start gap-3 bg-white/5 rounded-lg px-3 py-2 border border-white/10"
              >
                <span className="text-brand-electric font-bold text-sm mt-0.5">
                  {i + 1}
                </span>
                <p className="text-sm text-brand-silver">{trend}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Economic Indicators */}
      {econEntries.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Economic Indicators
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {econEntries.map((entry, i) => (
              <div
                key={i}
                className="glass-card p-3 rounded-lg text-center"
              >
                <p className="text-lg font-bold text-brand-electric">
                  {entry.value}
                </p>
                <p className="text-xs text-brand-silver/60 mt-1">
                  {entry.name}
                </p>
                {entry.date && (
                  <p className="text-xs text-brand-silver/40">{entry.date}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Key Findings */}
      {findings && findings.length > 0 && (() => {
        const filtered = findings.filter((f) => {
          if (typeof f !== 'string') return false;
          const trimmed = f.trim();
          if (!trimmed || trimmed.startsWith('{') || trimmed.startsWith('[')) return false;
          if (trimmed.split(/\s+/).length < 5) return false;
          if (/^completed \d+ tool calls?$/i.test(trimmed)) return false;
          if (/"[^"]+"\s*:/.test(trimmed)) return false;
          return true;
        });
        if (filtered.length === 0) return null;
        return (
          <section>
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
              Key Findings
            </h4>
            {filtered.map((f, i) => (
              <div key={i} className="mb-2">
                <MarkdownMessage content={f} />
              </div>
            ))}
          </section>
        );
      })()}

      {/* Recommendations */}
      {recommendations && recommendations.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Recommendations
          </h4>
          {recommendations.map((r, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={r} />
            </div>
          ))}
        </section>
      )}

      {/* Sources */}
      {sources && sources.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Sources ({sources.length})
          </h4>
          <div className="overflow-x-auto rounded-lg border border-white/10 max-h-64 overflow-y-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-brand-midnight text-xs text-brand-silver/60 uppercase sticky top-0 z-10">
                <tr>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {sources.map((src, i) => (
                  <tr key={i} className="hover:bg-white/5">
                    <td className="px-3 py-2 text-brand-silver/60 whitespace-nowrap capitalize text-xs">
                      {(src.type || 'web').replace(/_/g, ' ')}
                    </td>
                    <td className="px-3 py-2 text-brand-silver">
                      {src.url && /^https?:\/\//i.test(src.url) ? (
                        <a
                          href={src.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-electric hover:underline inline-flex items-center gap-1"
                        >
                          {src.title || src.url}
                          <ExternalLink className="w-3 h-3 flex-shrink-0" />
                        </a>
                      ) : (
                        <span>{src.title || '—'}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

/* ── CompetitorIntelligenceSection ──────────────────────────────────── */

function CompetitorIntelligenceSection({
  executiveSummary,
  competitors,
  competitorMatrix,
  swotAnalyses,
  positioningGaps,
  benchmarkingReport,
  sources,
  confidenceScore,
  findings,
  recommendations,
}: {
  executiveSummary?: string;
  competitors?: CIACompetitorProfile[];
  competitorMatrix?: Record<string, Record<string, number>>;
  swotAnalyses?: SWOTAnalysis[];
  positioningGaps?: PositioningGap[];
  benchmarkingReport?: Record<string, unknown>;
  sources?: SourceEntry[];
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  return (
    <div className="space-y-6">
      {/* Confidence badge */}
      {confidenceScore != null && confidenceScore > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
            Confidence
          </span>
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold ${
              confidenceScore >= 0.7
                ? 'bg-emerald-500/20 text-emerald-400'
                : confidenceScore >= 0.4
                  ? 'bg-amber-500/20 text-amber-400'
                  : 'bg-red-500/20 text-red-400'
            }`}
          >
            {Math.round(confidenceScore * 100)}%
          </span>
        </div>
      )}

      {/* Executive Summary */}
      {executiveSummary && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Executive Summary
          </h4>
          <div className="bg-white/5 rounded-lg p-4 border border-white/10">
            <MarkdownMessage content={executiveSummary} />
          </div>
        </section>
      )}

      {/* Competitor Profiles */}
      {competitors && competitors.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Competitors Analyzed ({competitors.length})
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {competitors.map((comp, i) => {
              const compAny = comp as unknown as Record<string, unknown>;
              const swot = compAny.swot as Record<string, unknown> | undefined;
              const reviewProfile = compAny.review_profile as Record<string, unknown> | undefined;
              const pricingProfile = compAny.pricing_profile as Record<string, unknown> | undefined;
              return (
                <div
                  key={i}
                  className="bg-white/5 rounded-lg p-4 border border-white/10"
                >
                  <h5 className="text-sm font-semibold text-white mb-1">
                    {comp.name}
                  </h5>
                  {comp.market_position && (
                    <p className="text-xs text-brand-electric/80 mb-1.5 line-clamp-2">
                      {comp.market_position}
                    </p>
                  )}
                  {comp.description && (
                    <p className="text-xs text-brand-silver/60 mb-2 line-clamp-3">
                      {comp.description}
                    </p>
                  )}
                  {/* Review summary */}
                  {reviewProfile != null && reviewProfile.avg_rating != null ? (
                    <p className="text-xs text-brand-silver/50 mb-1">
                      Rating: <span className="text-amber-400 font-medium">{String(reviewProfile.avg_rating)}/5</span>
                      {reviewProfile.total_reviews_estimated ? (
                        <span> ({String(reviewProfile.total_reviews_estimated)} reviews)</span>
                      ) : null}
                    </p>
                  ) : null}
                  {/* Pricing hint */}
                  {pricingProfile != null && pricingProfile.model_type ? (
                    <p className="text-xs text-brand-silver/50 mb-1">
                      Pricing: <span className="text-brand-silver font-medium capitalize">{String(pricingProfile.model_type)}</span>
                      {pricingProfile.has_free_tier ? ' (Free tier available)' : null}
                    </p>
                  ) : null}
                  {/* Inline SWOT mini-summary */}
                  {swot && (
                    <div className="mt-2 grid grid-cols-2 gap-1">
                      {Array.isArray(swot.strengths) && swot.strengths.length > 0 && (
                        <p className="text-xs text-emerald-400/80 line-clamp-1">
                          + {String(swot.strengths[0])}
                        </p>
                      )}
                      {Array.isArray(swot.weaknesses) && swot.weaknesses.length > 0 && (
                        <p className="text-xs text-red-400/80 line-clamp-1">
                          - {String(swot.weaknesses[0])}
                        </p>
                      )}
                    </div>
                  )}
                  {comp.website && (
                    <a
                      href={comp.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-brand-electric hover:underline inline-flex items-center gap-1 mt-2"
                    >
                      {comp.website.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}
                      <ExternalLink className="w-3 h-3 flex-shrink-0" />
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Competitor Matrix */}
      {competitorMatrix && Object.keys(competitorMatrix).length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Competitor Matrix
          </h4>
          <div className="overflow-x-auto rounded-lg border border-white/10">
            <table className="w-full text-sm text-left">
              <thead className="bg-brand-midnight text-xs text-brand-silver/60 uppercase sticky top-0 z-10">
                <tr>
                  <th className="px-3 py-2">Dimension</th>
                  {(() => {
                    const allCompetitors = new Set<string>();
                    Object.values(competitorMatrix).forEach((scores) => {
                      if (typeof scores === 'object' && scores) {
                        Object.keys(scores).forEach((k) => allCompetitors.add(k));
                      }
                    });
                    return Array.from(allCompetitors)
                      .slice(0, 8)
                      .map((name) => (
                        <th key={name} className="px-3 py-2 text-center">
                          {name}
                        </th>
                      ));
                  })()}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {Object.entries(competitorMatrix)
                  .slice(0, 10)
                  .map(([dimension, scores]) => {
                    const allCompetitors = new Set<string>();
                    Object.values(competitorMatrix).forEach((s) => {
                      if (typeof s === 'object' && s) {
                        Object.keys(s).forEach((k) => allCompetitors.add(k));
                      }
                    });
                    return (
                      <tr key={dimension} className="hover:bg-white/5">
                        <td className="px-3 py-2 text-brand-silver font-medium capitalize">
                          {dimension.replace(/_/g, ' ')}
                        </td>
                        {Array.from(allCompetitors)
                          .slice(0, 8)
                          .map((comp) => {
                            const score =
                              typeof scores === 'object' && scores
                                ? (scores as Record<string, number>)[comp]
                                : undefined;
                            return (
                              <td
                                key={comp}
                                className="px-3 py-2 text-center text-brand-silver"
                              >
                                {score != null ? (
                                  <span
                                    className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold ${
                                      score >= 8
                                        ? 'bg-emerald-500/20 text-emerald-400'
                                        : score >= 5
                                          ? 'bg-amber-500/20 text-amber-400'
                                          : 'bg-red-500/20 text-red-400'
                                    }`}
                                  >
                                    {score}
                                  </span>
                                ) : (
                                  <span className="text-brand-silver/30">-</span>
                                )}
                              </td>
                            );
                          })}
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* SWOT Analyses */}
      {swotAnalyses && swotAnalyses.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            SWOT Analyses
          </h4>
          <div className="space-y-4">
            {swotAnalyses.map((sw, i) => (
              <div
                key={i}
                className="bg-white/5 rounded-lg p-4 border border-white/10"
              >
                <h5 className="text-sm font-semibold text-white mb-3">
                  {sw.competitor}
                </h5>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {sw.strengths && sw.strengths.length > 0 && (
                    <div className="bg-emerald-500/10 rounded-lg p-3">
                      <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-2">
                        Strengths
                      </p>
                      <ul className="space-y-1">
                        {sw.strengths.slice(0, 5).map((s, j) => (
                          <li key={j} className="text-xs text-brand-silver flex gap-2">
                            <span className="text-emerald-400 mt-0.5">+</span>
                            <span>{s}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {sw.weaknesses && sw.weaknesses.length > 0 && (
                    <div className="bg-red-500/10 rounded-lg p-3">
                      <p className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2">
                        Weaknesses
                      </p>
                      <ul className="space-y-1">
                        {sw.weaknesses.slice(0, 5).map((w, j) => (
                          <li key={j} className="text-xs text-brand-silver flex gap-2">
                            <span className="text-red-400 mt-0.5">-</span>
                            <span>{w}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {sw.opportunities && sw.opportunities.length > 0 && (
                    <div className="bg-blue-500/10 rounded-lg p-3">
                      <p className="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-2">
                        Opportunities
                      </p>
                      <ul className="space-y-1">
                        {sw.opportunities.slice(0, 5).map((o, j) => (
                          <li key={j} className="text-xs text-brand-silver flex gap-2">
                            <span className="text-blue-400 mt-0.5">*</span>
                            <span>{o}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {sw.threats && sw.threats.length > 0 && (
                    <div className="bg-amber-500/10 rounded-lg p-3">
                      <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-2">
                        Threats
                      </p>
                      <ul className="space-y-1">
                        {sw.threats.slice(0, 5).map((t, j) => (
                          <li key={j} className="text-xs text-brand-silver flex gap-2">
                            <span className="text-amber-400 mt-0.5">!</span>
                            <span>{t}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Positioning Gaps */}
      {positioningGaps && positioningGaps.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Positioning Gap Analysis
          </h4>
          <div className="space-y-2">
            {positioningGaps.map((gap, i) => (
              <div
                key={i}
                className="bg-white/5 rounded-lg px-4 py-3 border border-white/10"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-white capitalize">
                      {gap.dimension?.replace(/_/g, ' ')}
                    </p>
                    {gap.gap_description && (
                      <p className="text-xs text-brand-silver/70 mt-1">
                        {gap.gap_description}
                      </p>
                    )}
                    {gap.evidence && (
                      <p className="text-xs text-brand-silver/50 mt-1 italic">
                        {gap.evidence}
                      </p>
                    )}
                  </div>
                  {gap.opportunity_score != null && (
                    <span
                      className={`inline-flex items-center justify-center w-10 h-10 rounded-full text-sm font-bold flex-shrink-0 ${
                        gap.opportunity_score >= 7
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : gap.opportunity_score >= 4
                            ? 'bg-amber-500/20 text-amber-400'
                            : 'bg-red-500/20 text-red-400'
                      }`}
                    >
                      {gap.opportunity_score}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Benchmarking Report */}
      {benchmarkingReport && Object.keys(benchmarkingReport).length > 0 && (() => {
        const benchSummary = benchmarkingReport.summary
          ? String(benchmarkingReport.summary)
          : '';
        const benchRankings: BenchmarkRanking[] = Array.isArray(
          benchmarkingReport.rankings
        )
          ? (benchmarkingReport.rankings as BenchmarkRanking[])
          : [];
        const benchDifferentiators: string[] = Array.isArray(
          benchmarkingReport.key_differentiators
        )
          ? (benchmarkingReport.key_differentiators as string[])
          : [];
        const benchDynamics = benchmarkingReport.market_dynamics
          ? String(benchmarkingReport.market_dynamics)
          : '';
        return (
          <section>
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
              Competitive Benchmarking
            </h4>
            {benchSummary && (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10 mb-4">
                <MarkdownMessage content={benchSummary} />
              </div>
            )}
            {benchRankings.length > 0 && (
              <div className="space-y-2 mb-4">
                {benchRankings.map((r, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 bg-white/5 rounded-lg px-4 py-2 border border-white/10"
                  >
                    <span className="text-brand-electric font-bold text-lg w-6 text-center">
                      {i + 1}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-white">
                        {r.competitor}
                      </p>
                      {r.tier && (
                        <span className="text-xs text-brand-silver/60 capitalize">
                          {r.tier}
                        </span>
                      )}
                    </div>
                    {r.overall_score != null && (
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-2 bg-white/10 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              r.overall_score >= 70
                                ? 'bg-emerald-400'
                                : r.overall_score >= 40
                                  ? 'bg-amber-400'
                                  : 'bg-red-400'
                            }`}
                            style={{ width: `${Math.min(r.overall_score, 100)}%` }}
                          />
                        </div>
                        <span className="text-sm font-bold text-brand-silver w-8 text-right">
                          {r.overall_score}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {benchDifferentiators.length > 0 && (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10 mb-4">
                <p className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                  Key Differentiators
                </p>
                <ul className="space-y-1">
                  {benchDifferentiators.map((d, i) => (
                    <li
                      key={i}
                      className="text-xs text-brand-silver flex gap-2"
                    >
                      <span className="text-brand-electric mt-0.5">*</span>
                      <span>{d}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {benchDynamics && (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <p className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                  Market Dynamics
                </p>
                <MarkdownMessage content={benchDynamics} />
              </div>
            )}
          </section>
        );
      })()}

      {/* Key Findings */}
      {findings && findings.length > 0 && (() => {
        const filtered = findings.filter((f) => {
          if (typeof f !== 'string') return false;
          const trimmed = f.trim();
          if (!trimmed || trimmed.startsWith('{') || trimmed.startsWith('[')) return false;
          if (trimmed.split(/\s+/).length < 5) return false;
          if (/^completed \d+ tool calls?$/i.test(trimmed)) return false;
          if (/"[^"]+"\s*:/.test(trimmed)) return false;
          return true;
        });
        if (filtered.length === 0) return null;
        return (
          <section>
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
              Key Findings
            </h4>
            {filtered.map((f, i) => (
              <div key={i} className="mb-2">
                <MarkdownMessage content={f} />
              </div>
            ))}
          </section>
        );
      })()}

      {/* Recommendations */}
      {recommendations && recommendations.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Recommendations
          </h4>
          {recommendations.map((r, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={r} />
            </div>
          ))}
        </section>
      )}

      {/* Sources */}
      {sources && sources.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Sources ({sources.length})
          </h4>
          <div className="overflow-x-auto rounded-lg border border-white/10 max-h-64 overflow-y-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-brand-midnight text-xs text-brand-silver/60 uppercase sticky top-0 z-10">
                <tr>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {sources.map((src, i) => (
                  <tr key={i} className="hover:bg-white/5">
                    <td className="px-3 py-2 text-brand-silver/60 whitespace-nowrap capitalize text-xs">
                      {(src.type || 'web').replace(/_/g, ' ')}
                    </td>
                    <td className="px-3 py-2 text-brand-silver">
                      {src.url && /^https?:\/\//i.test(src.url) ? (
                        <a
                          href={src.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-electric hover:underline inline-flex items-center gap-1"
                        >
                          {src.title || src.url}
                          <ExternalLink className="w-3 h-3 flex-shrink-0" />
                        </a>
                      ) : (
                        <span>{src.title || '-'}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

/* ── Audience Persona Types ──────────────────────────────────────── */

interface PersonaProfileFE {
  slug?: string;
  segment_label: string;
  data_source?: 'crm_grounded' | 'research_based';
  demographics?: Record<string, unknown>;
  psychographics?: Record<string, unknown>;
  pain_points?: string[];
  motivations?: string[];
  objections?: string[];
  preferred_channels?: string[];
  priority_score?: number;
  confidence_score?: number;
  narrative?: string;
  citations?: string[];
  requires_admin_review?: boolean;
}

interface JourneyStageFE {
  name: string;
  description?: string;
  touchpoints?: string[];
  info_needs?: string[];
  emotional_state?: string;
  decision_criteria?: string[];
  objections?: string[];
  content_recommendations?: string[];
  estimated_days?: number;
  key_actions?: string[];
}

interface BuyingJourneyMapFE {
  persona_slug?: string;
  persona_label: string;
  total_estimated_cycle_days?: number;
  stages: JourneyStageFE[];
}

/** Normalize a 0-1, 1-10, or 11-100 score to 0-1 range. */
function normalizeScore(v: number): number {
  if (v > 10) return v / 100;
  if (v > 1) return v / 10;
  return v;
}

/* ── AudiencePersonaSection (inline) ─────────────────────────────── */

function AudiencePersonaSection({
  executiveSummary,
  personas,
  journeyMaps,
  segmentMatrix,
  sources,
  confidenceScore,
  findings,
  recommendations,
}: {
  executiveSummary?: string;
  personas?: PersonaProfileFE[];
  journeyMaps?: BuyingJourneyMapFE[];
  segmentMatrix?: Record<string, unknown>;
  sources?: SourceEntry[];
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  const [expandedPersona, setExpandedPersona] = useState<string | null>(null);
  const [expandedJourney, setExpandedJourney] = useState<string | null>(null);

  const stageEmojis: Record<string, string> = {
    Awareness: '💡',
    Consideration: '🔍',
    Evaluation: '⚖️',
    Decision: '✅',
    Onboarding: '🚀',
    Advocacy: '❤️',
  };

  return (
    <div className="space-y-6">
      {/* Section Header */}
      <div className="flex items-center gap-2 border-b border-white/10 pb-2">
        <h4 className="font-heading text-sm font-semibold text-brand-electric">
          Audience &amp; Persona Analysis
        </h4>
        {confidenceScore != null && (() => {
          const normalized = normalizeScore(confidenceScore);
          return (
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                normalized >= 0.7
                  ? 'bg-green-500/20 text-green-400'
                  : normalized >= 0.4
                    ? 'bg-yellow-500/20 text-yellow-400'
                    : 'bg-red-500/20 text-red-400'
              }`}
            >
              Confidence: {(normalized * 100).toFixed(0)}%
            </span>
          );
        })()}
      </div>

      {/* Executive Summary */}
      {executiveSummary && (
        <section>
          <h5 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Executive Summary
          </h5>
          <MarkdownMessage content={executiveSummary} />
        </section>
      )}

      {/* Persona Cards */}
      {personas && personas.length > 0 && (
        <section>
          <h5 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Buyer Personas ({personas.length})
          </h5>
          <div className="grid gap-4 md:grid-cols-2">
            {personas.map((persona, idx) => {
              const isExpanded = expandedPersona === (persona.slug || `p-${idx}`);
              const toggleKey = persona.slug || `p-${idx}`;

              return (
                <div
                  key={toggleKey}
                  className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-3 cursor-pointer hover:border-brand-electric/30 transition-colors"
                  onClick={() => setExpandedPersona(isExpanded ? null : toggleKey)}
                >
                  {/* Header */}
                  <div className="flex items-start justify-between">
                    <div>
                      <h6 className="text-sm font-semibold text-white">
                        {persona.segment_label}
                      </h6>
                      <div className="flex items-center gap-2 mt-1">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                            persona.data_source === 'crm_grounded'
                              ? 'bg-blue-500/20 text-blue-400'
                              : 'bg-purple-500/20 text-purple-400'
                          }`}
                        >
                          {persona.data_source === 'crm_grounded' ? 'CRM Grounded' : 'Research Based'}
                        </span>
                        {persona.confidence_score != null && (
                          <span className="text-[10px] text-brand-silver/50">
                            {(normalizeScore(persona.confidence_score) * 100).toFixed(0)}% confidence
                          </span>
                        )}
                        {persona.requires_admin_review && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] text-amber-400">
                            <AlertCircle className="w-3 h-3" /> Admin Review
                          </span>
                        )}
                      </div>
                    </div>
                    {persona.priority_score != null && (
                      <span className="text-xs text-brand-silver/50">
                        Priority: {(normalizeScore(persona.priority_score) * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>

                  {/* Pain Points & Motivations (always visible) */}
                  {persona.pain_points && persona.pain_points.length > 0 && (
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Pain Points</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {persona.pain_points.slice(0, isExpanded ? undefined : 3).map((pp, i) => (
                          <span key={i} className="rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] text-red-400">
                            {pp}
                          </span>
                        ))}
                        {!isExpanded && persona.pain_points.length > 3 && (
                          <span className="text-[11px] text-brand-silver/40">+{persona.pain_points.length - 3} more</span>
                        )}
                      </div>
                    </div>
                  )}

                  {persona.motivations && persona.motivations.length > 0 && (
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Motivations</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {persona.motivations.slice(0, isExpanded ? undefined : 3).map((m, i) => (
                          <span key={i} className="rounded-full bg-green-500/10 px-2 py-0.5 text-[11px] text-green-400">
                            {m}
                          </span>
                        ))}
                        {!isExpanded && persona.motivations.length > 3 && (
                          <span className="text-[11px] text-brand-silver/40">+{persona.motivations.length - 3} more</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Expanded Content */}
                  {isExpanded && (
                    <div className="space-y-3 pt-2 border-t border-white/5">
                      {/* Demographics Grid */}
                      {persona.demographics && Object.keys(persona.demographics).length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Demographics</span>
                          <div className="grid grid-cols-2 gap-2 mt-1">
                            {Object.entries(persona.demographics).map(([key, val]) => (
                              <div key={key} className="text-[11px]">
                                <span className="text-brand-silver/50 capitalize">{key.replace(/_/g, ' ')}: </span>
                                <span className="text-brand-silver">
                                  {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Psychographics */}
                      {persona.psychographics && Object.keys(persona.psychographics).length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Psychographics</span>
                          <div className="grid grid-cols-2 gap-2 mt-1">
                            {Object.entries(persona.psychographics).map(([key, val]) => (
                              <div key={key} className="text-[11px]">
                                <span className="text-brand-silver/50 capitalize">{key.replace(/_/g, ' ')}: </span>
                                <span className="text-brand-silver">
                                  {Array.isArray(val) ? val.join(', ') : typeof val === 'object' ? JSON.stringify(val) : String(val)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Objections */}
                      {persona.objections && persona.objections.length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Objections</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {persona.objections.map((o, i) => (
                              <span key={i} className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-400">
                                {o}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Preferred Channels */}
                      {persona.preferred_channels && persona.preferred_channels.length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Preferred Channels</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {persona.preferred_channels.map((ch, i) => (
                              <span key={i} className="rounded-full bg-brand-electric/10 px-2 py-0.5 text-[11px] text-brand-electric">
                                {ch}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Narrative */}
                      {persona.narrative && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Narrative</span>
                          <div className="mt-1 text-[12px] text-brand-silver/80 leading-relaxed">
                            <MarkdownMessage content={persona.narrative} />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Buying Journey Timelines */}
      {journeyMaps && journeyMaps.length > 0 && (
        <section>
          <h5 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Buying Journey Maps
          </h5>
          <div className="space-y-4">
            {journeyMaps.map((journey, idx) => {
              const jKey = journey.persona_slug || `j-${idx}`;
              const isJExpanded = expandedJourney === jKey;

              return (
                <div
                  key={jKey}
                  className="rounded-lg border border-white/10 bg-white/5 p-4 space-y-3"
                >
                  <div
                    className="flex items-center justify-between cursor-pointer"
                    onClick={() => setExpandedJourney(isJExpanded ? null : jKey)}
                  >
                    <h6 className="text-sm font-semibold text-white">
                      {journey.persona_label}
                    </h6>
                    {journey.total_estimated_cycle_days != null && (
                      <span className="text-xs text-brand-silver/50">
                        ~{journey.total_estimated_cycle_days} days
                      </span>
                    )}
                  </div>

                  {/* Stage Timeline */}
                  <div className="flex items-center gap-1 overflow-x-auto">
                    {journey.stages.map((stage, si) => (
                      <div key={si} className="flex items-center">
                        <div className="flex flex-col items-center min-w-[80px]">
                          <span className="text-lg">
                            {stageEmojis[stage.name] || '📌'}
                          </span>
                          <span className="text-[10px] text-brand-silver/70 text-center mt-0.5">
                            {stage.name}
                          </span>
                          {stage.estimated_days != null && (
                            <span className="text-[9px] text-brand-silver/40">
                              {stage.estimated_days}d
                            </span>
                          )}
                        </div>
                        {si < journey.stages.length - 1 && (
                          <div className="w-4 h-px bg-white/20 mx-0.5" />
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Expanded Stage Details */}
                  {isJExpanded && (
                    <div className="space-y-3 pt-2 border-t border-white/5">
                      {journey.stages.map((stage, si) => (
                        <div key={si} className="rounded border border-white/5 bg-white/[0.02] p-3 space-y-2">
                          <div className="flex items-center gap-2">
                            <span>{stageEmojis[stage.name] || '📌'}</span>
                            <span className="text-xs font-semibold text-white">{stage.name}</span>
                            {stage.emotional_state && (
                              <span className="text-[10px] text-brand-silver/50 italic">
                                Feeling: {stage.emotional_state}
                              </span>
                            )}
                          </div>

                          {stage.description && (
                            <p className="text-[11px] text-brand-silver/70">{stage.description}</p>
                          )}

                          <div className="grid grid-cols-2 gap-2">
                            {stage.touchpoints && stage.touchpoints.length > 0 && (
                              <div>
                                <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Touchpoints</span>
                                <ul className="mt-0.5 space-y-0.5">
                                  {stage.touchpoints.map((tp, ti) => (
                                    <li key={ti} className="text-[10px] text-brand-silver/60">• {tp}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {stage.content_recommendations && stage.content_recommendations.length > 0 && (
                              <div>
                                <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Content Recs</span>
                                <ul className="mt-0.5 space-y-0.5">
                                  {stage.content_recommendations.map((cr, ci) => (
                                    <li key={ci} className="text-[10px] text-brand-silver/60">• {cr}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>

                          {stage.objections && stage.objections.length > 0 && (
                            <div>
                              <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Objections at this stage</span>
                              <div className="flex flex-wrap gap-1 mt-0.5">
                                {stage.objections.map((obj, oi) => (
                                  <span key={oi} className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-400">{obj}</span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Segment Matrix */}
      {segmentMatrix && Object.keys(segmentMatrix).length > 0 && (
        <section>
          <h5 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Segment Matrix
          </h5>
          <div className="space-y-3">
            {Object.entries(segmentMatrix).map(([dimension, val]) => (
              <div key={dimension} className="rounded-lg border border-white/10 bg-white/5 p-3">
                <h6 className="text-xs font-semibold text-white capitalize mb-2">
                  {dimension.replace(/_/g, ' ')}
                </h6>
                {val && typeof val === 'object' && !Array.isArray(val) ? (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(val as Record<string, unknown>).map(([group, members]) => (
                      <div key={group} className="rounded-md bg-white/5 border border-white/10 px-2.5 py-1.5">
                        <span className="text-[10px] font-medium text-brand-electric capitalize">
                          {group.replace(/_/g, ' ')}
                        </span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {(Array.isArray(members) ? members : [members]).map((m, i) => (
                            <span key={i} className="rounded-full bg-brand-electric/10 px-2 py-0.5 text-[10px] text-brand-silver capitalize">
                              {String(m).replace(/-/g, ' ')}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : Array.isArray(val) ? (
                  <div className="flex flex-wrap gap-1">
                    {(val as string[]).map((item, i) => (
                      <span key={i} className="rounded-full bg-brand-electric/10 px-2 py-0.5 text-[10px] text-brand-silver capitalize">
                        {String(item).replace(/-/g, ' ')}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-brand-silver">{String(val)}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Findings & Recommendations */}
      {findings && findings.length > 0 && (
        <section>
          <h5 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Key Findings
          </h5>
          {findings.filter((f) => typeof f === 'string' && f.trim().length > 10 && !f.trim().startsWith('{')).map((f, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={f} />
            </div>
          ))}
        </section>
      )}

      {recommendations && recommendations.length > 0 && (
        <section>
          <h5 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Recommendations
          </h5>
          {recommendations.filter((r) => typeof r === 'string' && r.trim().length > 0).map((r, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={r} />
            </div>
          ))}
        </section>
      )}

      {/* Sources Table */}
      {sources && sources.length > 0 && (
        <section>
          <h5 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Sources ({sources.length})
          </h5>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="px-3 py-2 text-brand-silver/60 font-medium">Type</th>
                  <th className="px-3 py-2 text-brand-silver/60 font-medium">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {sources.map((src, i) => (
                  <tr key={i} className="hover:bg-white/5">
                    <td className="px-3 py-2 text-brand-silver/60 whitespace-nowrap capitalize text-xs">
                      {(src.type || 'web').replace(/_/g, ' ')}
                    </td>
                    <td className="px-3 py-2 text-brand-silver">
                      {src.url && /^https?:\/\//i.test(src.url) ? (
                        <a
                          href={src.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-electric hover:underline inline-flex items-center gap-1"
                        >
                          {src.title || src.url}
                          <ExternalLink className="w-3 h-3 flex-shrink-0" />
                        </a>
                      ) : (
                        <span>{src.title || '-'}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

export default function ResultDashboard({
  resultData,
  manifestName,
}: ResultDashboardProps) {
  // Route to specialized dashboard for Brand Equity / ISO pipelines.
  // Detect by manifest name OR by result_data shape (chat pipelines
  // use auto-detect mode and have no manifest, but produce identical data).
  const isBrandEquityByName =
    manifestName &&
    (/brand.?equity/i.test(manifestName) || /iso/i.test(manifestName));
  const isBrandEquityByContent =
    resultData.valuation != null &&
    typeof resultData.score === 'number' &&
    resultData.score > 0;

  if (isBrandEquityByName || isBrandEquityByContent) {
    return <BrandEquityDashboard resultData={resultData} />;
  }

  // ── Detect market research data ──────────────────────────────────
  const hasMarketResearch =
    resultData.market_sizing != null || resultData.market_overview != null;

  // ── Detect competitor intelligence data ────────────────────────
  const hasCompetitorIntelligence =
    resultData.competitors != null ||
    resultData.competitor_matrix != null ||
    resultData.swot_analyses != null;

  // ── Detect audience persona data ─────────────────────────────
  const hasAudiencePersona =
    resultData.personas != null || resultData.journey_maps != null;

  // ── Extract well-known keys ──────────────────────────────────────
  const summary = resultData.summary as string | undefined;
  const findings = resultData.findings as string[] | undefined;
  const recommendations = resultData.recommendations as string[] | undefined;
  const score = resultData.score as number | undefined;

  // ── Extract blog + social + odoo from node_results ────────────────
  const nodeResults = resultData.node_results as
    | Record<string, Record<string, unknown>>
    | undefined;
  const blogOutput = nodeResults?.blog_author as
    | Record<string, unknown>
    | undefined;
  const socialOutput = nodeResults?.social_promoter as
    | Record<string, unknown>
    | undefined;
  // Collect ALL Odoo-related node outputs (generic + persona-specific)
  const ODOO_NODE_PREFIXES = ['odoo_worker', 'odoo_sales_crm', 'odoo_finance', 'odoo_inventory', 'odoo_hr', 'odoo_marketing', 'odoo_manufacturing'];
  // Schema/metadata tools that produce huge JSON — never display
  const metadataToolNames = new Set(['odoo_get_fields', 'odoo_get_metadata', 'odoo_fields_get']);
  // Global dedup for ID-only cards across all entries
  const globalSeenIdCards = new Set<string>();
  const odooEntries: Array<{
    nodeId: string;
    output: Record<string, unknown>;
    data: Record<string, unknown> | undefined;
    toolResults: Array<{ tool_name: string; data: Record<string, unknown> }>;
    finalAnswer: string | undefined;
    persona: string | undefined;
  }> = [];

  if (nodeResults) {
    for (const prefix of ODOO_NODE_PREFIXES) {
      const output = nodeResults[prefix] as Record<string, unknown> | undefined;
      if (!output) continue;
      const data = output.data as Record<string, unknown> | undefined;
      const rawToolResults = (data?.tool_results ?? []) as Array<{
        tool_name: string;
        data: Record<string, unknown>;
      }>;

      // ── Pre-filter tool results (same criteria as render-time) ──
      const toolResults = rawToolResults.filter((tr) => {
        if (tr.data?.success === false) return false;
        if (metadataToolNames.has(tr.tool_name)) return false;
        const innerRes = tr.data?.result as Record<string, unknown> | undefined;
        if (innerRes && typeof innerRes.error === 'string' && innerRes.error) return false;
        // Global dedup for ID-only results
        if (innerRes && Array.isArray(innerRes.ids) && innerRes.count != null) {
          const dedupeKey = `${innerRes.model ?? ''}:${innerRes.count}`;
          if (globalSeenIdCards.has(dedupeKey)) return false;
          globalSeenIdCards.add(dedupeKey);
        }
        return true;
      });

      let finalAnswer = data?.final_answer as string | undefined;
      // Suppress internal agent metadata from final answer
      if (finalAnswer) {
        const trimmedFA = finalAnswer.trim();
        if (/^reached maximum reasoning steps/i.test(trimmedFA)) {
          finalAnswer = undefined;
        }
        // Suppress raw agent loop state leaked as final_answer string
        if (trimmedFA.startsWith('{')) {
          try {
            const parsed = JSON.parse(trimmedFA);
            if (parsed && typeof parsed === 'object' &&
              ('tool_calls' in parsed || 'is_complete' in parsed || 'thought' in parsed)) {
              finalAnswer = undefined;
            }
          } catch {
            // Not valid JSON — keep as-is
          }
        }
      }
      const persona = (output.persona_used ??
        (output.result_data as Record<string, unknown> | undefined)
          ?.persona) as string | undefined;

      // Check for extractable next_actions content (fallback render path)
      const nextActions = (data as Record<string, unknown> | undefined)?.next_actions as
        | Array<{ arguments: Record<string, string> }>
        | undefined;
      const hasNextActionsContent = nextActions?.some(
        (a) => typeof a.arguments?.content === 'string') ?? false;

      // Skip entries with no renderable content
      const hasContent = !!finalAnswer || toolResults.length > 0 || hasNextActionsContent;
      if (!hasContent) continue;
      odooEntries.push({
        nodeId: prefix,
        output,
        data,
        toolResults,
        finalAnswer,
        persona,
      });
    }
  }

  const blogContent = blogOutput?.blog_content as string | undefined;
  const publishResults = (socialOutput?.publish_results ?? []) as PublishResultEntry[];
  const draftStored = socialOutput?.draft_stored as boolean | undefined;

  // ── Suppress technical keys from "Other sections" ────────────────
  const knownKeys = new Set([
    'summary',
    'findings',
    'recommendations',
    'score',
    'node_results',
    'awareness',
    'sentiment',
    'financials',
    'valuation',
    'ui_schema',
    'market_overview',
    'market_sizing',
    'competitive_landscape',
    'industry_trends',
    'economic_indicators',
    'sources',
    'confidence_score',
    'methodology_notes',
    // Competitor Intelligence keys
    'competitors',
    'competitors_analyzed',
    'competitor_matrix',
    'swot_analyses',
    'positioning_gaps',
    'positioning_map',
    'benchmarking_report',
    'executive_summary',
    'query',
    'raw_context',
    // Audience Persona keys
    'personas',
    'journey_maps',
    'segment_matrix',
  ]);
  const otherEntries = Object.entries(resultData).filter(
    ([k]) => !knownKeys.has(k),
  );

  return (
    <div className="glass-card p-6 space-y-6">
      {/* Header + single toolbar for entire response */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-heading font-semibold text-white">
          Analysis Results
        </h3>
        <DataToolbar
          content={resultDataToText(resultData)}
          title="Analysis Results"
          format="text"
        />
      </div>

      {/* Score badge (only when meaningful, i.e. > 0, and not market research) */}
      {!hasMarketResearch && !hasCompetitorIntelligence && !hasAudiencePersona && score !== undefined && score > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
            Score
          </span>
          <span className="inline-flex items-center rounded-full bg-brand-electric/20 px-3 py-1 text-sm font-bold text-brand-electric">
            {score}
          </span>
        </div>
      )}

      {/* Summary (skip generic "Pipeline analysis completed" for market research / CIA) */}
      {summary && !hasMarketResearch && !hasCompetitorIntelligence && !hasAudiencePersona && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Summary
          </h4>
          <MarkdownMessage content={summary} />
        </section>
      )}

      {/* ── Market Research Dashboard ──────────────────────────────── */}
      {hasMarketResearch && (
        <MarketResearchSection
          marketOverview={resultData.market_overview as string | undefined}
          marketSizing={resultData.market_sizing as Record<string, unknown> | undefined}
          competitiveLandscape={resultData.competitive_landscape as CompetitorEntry[] | undefined}
          industryTrends={resultData.industry_trends as string[] | undefined}
          economicIndicators={resultData.economic_indicators as Record<string, unknown> | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          confidenceScore={resultData.confidence_score as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {/* ── Competitor Intelligence Dashboard ──────────────────────── */}
      {hasCompetitorIntelligence && (
        <CompetitorIntelligenceSection
          executiveSummary={resultData.executive_summary as string | undefined}
          competitors={resultData.competitors as CIACompetitorProfile[] | undefined}
          competitorMatrix={resultData.competitor_matrix as Record<string, Record<string, number>> | undefined}
          swotAnalyses={resultData.swot_analyses as SWOTAnalysis[] | undefined}
          positioningGaps={resultData.positioning_gaps as PositioningGap[] | undefined}
          benchmarkingReport={resultData.benchmarking_report as Record<string, unknown> | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          confidenceScore={resultData.confidence_score as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {/* ── Audience Persona Dashboard ─────────────────────────────── */}
      {hasAudiencePersona && (
        <AudiencePersonaSection
          executiveSummary={resultData.executive_summary as string | undefined}
          personas={resultData.personas as PersonaProfileFE[] | undefined}
          journeyMaps={resultData.journey_maps as BuyingJourneyMapFE[] | undefined}
          segmentMatrix={resultData.segment_matrix as Record<string, unknown> | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          confidenceScore={resultData.confidence_score as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {/* Key findings — filter out raw JSON blobs (internal agent state) */}
      {!hasMarketResearch && !hasCompetitorIntelligence && !hasAudiencePersona && findings && findings.length > 0 && (() => {
        const filtered = findings.filter((f) => {
          if (typeof f !== 'string') return false;
          const trimmed = f.trim();
          if (!trimmed) return false;
          // Skip items that look like raw JSON objects/arrays
          if (trimmed.startsWith('{') || trimmed.startsWith('[')) return false;
          // Real findings are sentences — require at least 5 words
          const words = trimmed.split(/\s+/);
          if (words.length < 5) return false;
          // Skip agent metadata (e.g. "Completed 5 tool calls")
          if (/^completed \d+ tool calls?$/i.test(trimmed)) return false;
          // Skip strings with JSON key-value patterns
          if (/"[^"]+"\s*:/.test(trimmed)) return false;
          return true;
        });
        if (filtered.length === 0) return null;
        return (
          <section>
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
              Key Findings
            </h4>
            {filtered.map((f, i) => (
              <div key={i} className="mb-2">
                <MarkdownMessage content={f} />
              </div>
            ))}
          </section>
        );
      })()}

      {/* Recommendations */}
      {!hasMarketResearch && !hasCompetitorIntelligence && !hasAudiencePersona && recommendations && recommendations.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Recommendations
          </h4>
          {recommendations.map((r, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={r} />
            </div>
          ))}
        </section>
      )}

      {/* ── Blog Post (rendered markdown with copy / export) ──────── */}
      {blogContent && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Blog Post
          </h4>
          <div className="bg-white/5 rounded-lg p-4 border border-white/10 max-h-[32rem] overflow-y-auto">
            <MarkdownMessage content={blogContent} />
          </div>
        </section>
      )}

      {/* ── Social Promotion status ──────────────────────────────── */}
      {publishResults.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Social Promotion
          </h4>
          <div className="space-y-2">
            {publishResults.map((pr, i) => (
              <div
                key={i}
                className="flex items-center justify-between bg-white/5 rounded-lg px-3 py-2 border border-white/10"
              >
                <span className="text-sm font-medium text-white capitalize">
                  {pr.platform}
                </span>
                <div className="flex items-center gap-3">
                  {pr.status === 'published' && (
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400">
                      <Check className="w-3.5 h-3.5" /> Published
                    </span>
                  )}
                  {pr.status === 'scheduled' && (
                    <span className="text-xs font-medium text-brand-electric">
                      Scheduled
                      {pr.scheduled_date
                        ? ` — ${formatScheduledDate(pr.scheduled_date)}`
                        : ''}
                    </span>
                  )}
                  {pr.status === 'draft' && (
                    <span className="text-xs font-medium text-amber-400">
                      Draft — pending approval
                    </span>
                  )}
                  {pr.status === 'failed' && (
                    <span className="text-xs font-medium text-red-400">
                      Failed{pr.error ? `: ${pr.error}` : ''}
                    </span>
                  )}
                  {pr.post_url &&
                    /^https?:\/\//i.test(pr.post_url) && (
                      <a
                        href={pr.post_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-brand-electric hover:underline"
                      >
                        View <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                </div>
              </div>
            ))}
          </div>
          {draftStored && (
            <p className="text-xs text-brand-silver/60 mt-2">
              Drafts saved for admin approval.
            </p>
          )}
        </section>
      )}

      {/* ── Odoo ERP Results (supports multi-persona workers) ──── */}
      {odooEntries.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Odoo ERP Results
          </h4>

          {odooEntries.map((entry) => (
            <div key={entry.nodeId} className="mb-6 last:mb-0">
              {/* Persona badge — show nodeId when persona duplicates exist */}
              <div className="flex items-center gap-2 mb-3">
                <span className="inline-flex items-center rounded-full bg-brand-electric/20 px-2 py-0.5 text-xs font-medium text-brand-electric capitalize">
                  {entry.nodeId.replace(/_/g, ' ')}
                </span>
                {entry.persona && entry.persona !== entry.nodeId && (
                  <span className="text-xs text-brand-silver/50">
                    ({entry.persona.replace(/_/g, ' ')})
                  </span>
                )}
              </div>

              {/* ── Email Campaign KPI Dashboard ── */}
              {(() => {
                const campaignResults = entry.toolResults.filter(
                  (tr) => tr.tool_name === 'marketing_create_campaign' && tr.data?.success !== false,
                );
                if (campaignResults.length === 0) return null;
                return (
                  <div className="mb-4">
                    <p className="text-xs text-brand-silver/60 mb-3 font-semibold uppercase tracking-wider">
                      Email Campaign KPIs
                    </p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                      {campaignResults.map((cr, ci) => {
                        const result = (cr.data?.result ?? cr.data) as Record<string, unknown>;
                        const campaignId = result?.id ?? result?.campaign_id;
                        const model = result?.model ?? 'mailing.mailing';
                        return (
                          <div key={ci} className="contents">
                            <div className="glass-card p-3 rounded-lg text-center">
                              <p className="text-2xl font-bold text-brand-electric">
                                {String(campaignId ?? '—')}
                              </p>
                              <p className="text-xs text-brand-silver/60 mt-1">Campaign ID</p>
                            </div>
                            <div className="glass-card p-3 rounded-lg text-center">
                              <p className="text-2xl font-bold text-green-400">Draft</p>
                              <p className="text-xs text-brand-silver/60 mt-1">Status</p>
                            </div>
                            <div className="glass-card p-3 rounded-lg text-center">
                              <p className="text-2xl font-bold text-brand-silver">{String(model)}</p>
                              <p className="text-xs text-brand-silver/60 mt-1">Model</p>
                            </div>
                            <div className="glass-card p-3 rounded-lg text-center">
                              <p className="text-2xl font-bold text-amber-400">Ready</p>
                              <p className="text-xs text-brand-silver/60 mt-1">Send Status</p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <p className="text-sm text-brand-silver/70 italic">
                      Refer to the Odoo Email Marketing dashboard for detailed campaign KPIs including delivery rate, open rate, click-through rate, and bounce metrics.
                    </p>
                  </div>
                );
              })()}

              {/* ── Recipient count KPI ── */}
              {(() => {
                const recipientResults = entry.toolResults.filter(
                  (tr) =>
                    tr.tool_name === 'odoo_search_read' &&
                    tr.data?.success !== false &&
                    ((tr.data?.result as Record<string, unknown>)?.model === 'res.partner' ||
                      (tr.data?.model as string) === 'res.partner'),
                );
                const recipientCount = recipientResults.reduce((sum, rr) => {
                  const result = (rr.data?.result ?? rr.data) as Record<string, unknown>;
                  return sum + (Number(result?.count) || 0);
                }, 0);
                if (recipientCount === 0) return null;
                return (
                  <div className="mb-4 glass-card p-4 rounded-lg">
                    <div className="flex items-center gap-4">
                      <div>
                        <p className="text-3xl font-bold text-brand-electric">{recipientCount}</p>
                        <p className="text-xs text-brand-silver/60">Target Recipients</p>
                      </div>
                      <div className="h-10 w-px bg-white/10" />
                      <p className="text-sm text-brand-silver/70">
                        Customer email addresses found for the campaign mailing list.
                      </p>
                    </div>
                  </div>
                );
              })()}

              {/* Final answer */}
              {entry.finalAnswer && (
                <div className="mb-4">
                  <MarkdownMessage content={entry.finalAnswer} />
                </div>
              )}

              {/* ── Successful tool results as tables ── */}
              {entry.toolResults.length > 0 && (
                <div className="space-y-4">
                  {entry.toolResults
                    .filter((tr) => tr.tool_name !== 'marketing_create_campaign')
                    .map((tr, idx) => {
                    const innerResult = tr.data?.result as Record<string, unknown> | undefined;
                    // Find records array: check known keys (records, orders,
                    // employees, etc.) then fall back to first array field
                    const findRecords = (obj: Record<string, unknown> | undefined): Array<Record<string, unknown>> | null => {
                      if (!obj) return null;
                      // Check explicit key first
                      if (Array.isArray(obj.records) && obj.records.length > 0) return obj.records as Array<Record<string, unknown>>;
                      // Search for the first array of objects
                      for (const val of Object.values(obj)) {
                        if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'object' && val[0] !== null) {
                          return val as Array<Record<string, unknown>>;
                        }
                      }
                      return null;
                    };
                    const records = findRecords(innerResult) ?? findRecords(tr.data);
                    if (records && records.length > 0) {
                      const columns = Object.keys(records[0]).filter(
                        (k) => k !== 'id' && !k.startsWith('_'),
                      );
                      const csvCell = (v: unknown): string => {
                        const s = Array.isArray(v)
                          ? String((v as unknown[])[1] ?? (v as unknown[])[0])
                          : typeof v === 'object' && v !== null
                            ? JSON.stringify(v)
                            : String(v ?? '');
                        return /[,"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
                      };
                      const csvContent = [
                        columns.join(','),
                        ...records.map((row) => columns.map((c) => csvCell(row[c])).join(',')),
                      ].join('\n');
                      return (
                        <div key={idx}>
                          <p className="text-xs text-brand-silver/60 mb-2 font-medium">
                            {tr.tool_name.replace(/_/g, ' ')}
                            <span className="ml-2 text-brand-silver/40">
                              ({records.length} records)
                            </span>
                          </p>
                          <div className="overflow-x-auto rounded-lg border border-white/10 max-h-96 overflow-y-auto">
                            <table className="w-full text-sm text-left">
                              <thead className="bg-brand-midnight text-xs text-brand-silver/60 uppercase sticky top-0 z-10">
                                <tr>
                                  {columns.map((col) => (
                                    <th key={col} className="px-3 py-2">
                                      {col.replace(/_/g, ' ')}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-white/5">
                                {records.map((row, ri) => (
                                  <tr key={ri} className="hover:bg-white/5">
                                    {columns.map((col) => (
                                      <td
                                        key={col}
                                        className="px-3 py-2 text-brand-silver whitespace-nowrap"
                                      >
                                        {Array.isArray(row[col])
                                          ? String((row[col] as unknown[])[1] ?? (row[col] as unknown[])[0])
                                          : typeof row[col] === 'object' && row[col] !== null
                                            ? JSON.stringify(row[col])
                                            : String(row[col] ?? '')}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      );
                    }
                    // Summarise ID-only results (e.g. odoo_search returning just ids)
                    const idResult = innerResult ?? tr.data?.result as Record<string, unknown> | undefined;
                    if (idResult && Array.isArray(idResult.ids) && idResult.count != null) {
                      const modelName = idResult.model ? String(idResult.model).replace(/\./g, ' ') : 'records';
                      return (
                        <div key={idx} className="glass-card p-3 rounded-lg flex items-center gap-3">
                          <p className="text-2xl font-bold text-brand-electric">{String(idResult.count)}</p>
                          <div>
                            <p className="text-sm font-medium text-brand-silver capitalize">{modelName}</p>
                            <p className="text-xs text-brand-silver/50">{tr.tool_name.replace(/_/g, ' ')}</p>
                          </div>
                        </div>
                      );
                    }
                    // Fallback: render non-error, non-internal results as JSON
                    if (tr.data && !tr.data?.error) {
                      // Skip raw JSON that is just internal metadata
                      const hasInternalKeys = tr.data.reflection != null || tr.data.is_complete != null;
                      if (hasInternalKeys) return null;
                      // Skip excessively large JSON (e.g. schema dumps)
                      const jsonStr = JSON.stringify(tr.data, null, 2);
                      if (jsonStr.length > 2000) return null;
                      return (
                        <div key={idx}>
                          <p className="text-xs text-brand-silver/60 mb-1 font-medium">
                            {tr.tool_name.replace(/_/g, ' ')}
                          </p>
                          <pre className="text-xs text-brand-silver/80 bg-white/5 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                            {jsonStr}
                          </pre>
                        </div>
                      );
                    }
                    return null;
                  })}
                </div>
              )}

              {/* ── Fallback: no tool_results → extract content from raw data ── */}
              {entry.toolResults.length === 0 && !entry.finalAnswer && entry.data && (() => {
                // Internal agent state keys to suppress (not user-facing)
                const internalKeys = new Set(['reflection', 'is_complete', 'next_actions', 'tool_calls']);
                const dataKeys = Object.keys(entry.data as Record<string, unknown>);
                const isInternalState = dataKeys.some((k) => internalKeys.has(k));

                if (isInternalState) {
                  // Try to extract content from next_actions
                  const nextActions = (entry.data as Record<string, unknown>).next_actions as
                    | Array<{ tool_name: string; arguments: Record<string, string> }>
                    | undefined;
                  if (nextActions && nextActions.length > 0) {
                    const contentActions = nextActions.filter(
                      (a) => typeof a.arguments?.content === 'string',
                    );
                    if (contentActions.length > 0) {
                      return (
                        <div className="space-y-3">
                          {contentActions.map((a, ai) => (
                            <div key={ai} className="bg-white/5 rounded-lg p-4 border border-white/10">
                              {a.arguments.title && (
                                <p className="text-xs text-brand-silver/60 mb-2 font-medium">
                                  {String(a.arguments.title)}
                                </p>
                              )}
                              <MarkdownMessage content={String(a.arguments.content)} />
                            </div>
                          ))}
                        </div>
                      );
                    }
                  }
                  // Internal state with no extractable content — skip
                  return null;
                }
                return null;
              })()}
            </div>
          ))}
        </section>
      )}

      {/* Other sections (anything not already handled above) */}
      {otherEntries.map(([key, value]) => (
        <section key={key}>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            {sectionTitle(key)}
          </h4>
          {renderValue(value)}
        </section>
      ))}
    </div>
  );
}
