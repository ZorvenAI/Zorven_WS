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
  CheckCircle2,
  ExternalLink,
  Loader2,
  BookmarkPlus,
  BookmarkCheck,
  AlertCircle,
  LayoutDashboard,
  Users,
  Image,
  DollarSign,
  ChevronDown,
  ChevronRight,
  Target,
  Megaphone,
  Layers,
} from 'lucide-react';
import { apiClient } from '@/lib/api';
import { linkFromChat } from '@/lib/workspace';
import BrandEquityDashboard from './BrandEquityDashboard';
import ApprovalPanel from './ApprovalPanel';
import { MarkdownMessage } from '@/components/chat/MarkdownMessage';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';

interface ResultDashboardProps {
  resultData: Record<string, unknown>;
  /** Optional manifest name — used to route to specialized dashboards. */
  manifestName?: string | null;
  /** Job ID — enables "Save to Workspace" button when provided. */
  jobId?: string | null;
  /** Chat session ID — required together with jobId for Save to Workspace. */
  chatSessionId?: string | null;
  /** Current job status — used to show approval UI for awaiting_approval. */
  jobStatus?: string | null;
  /** Called when approval action completes (approve/reject). */
  onApprovalComplete?: () => void;
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
  /** Job ID — enables "Save to Workspace" button. */
  jobId?: string | null;
  /** Chat session ID for workspace link. */
  chatSessionId?: string | null;
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

function DataToolbar({ content, title, format = 'text', jobId, chatSessionId }: DataToolbarProps) {
  const [copied, setCopied] = useState(false);
  const [ragSaveState, setRagSaveState] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');
  const [wsSaveState, setWsSaveState] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');
  const [savedWorkflowId, setSavedWorkflowId] = useState<string | null>(null);

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

  const handleSaveToWorkspace = async () => {
    if (wsSaveState === 'saving' || !jobId || !chatSessionId) return;
    setWsSaveState('saving');
    try {
      const result = await linkFromChat({
        job_id: jobId,
        chat_session_id: chatSessionId,
      });
      setSavedWorkflowId(result.workflow_id);
      setWsSaveState('saved');
    } catch {
      setWsSaveState('error');
    }
    setTimeout(() => setWsSaveState('idle'), 3000);
  };

  return (
    <div className="flex gap-2 mb-2 flex-wrap">
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
      {jobId && chatSessionId && (
        <button
          onClick={handleSaveToWorkspace}
          disabled={wsSaveState === 'saving' || wsSaveState === 'saved'}
          className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5 disabled:opacity-60"
        >
          {wsSaveState === 'saving' && (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          )}
          {wsSaveState === 'saved' && (
            <Check className="w-3.5 h-3.5 text-emerald-400" />
          )}
          {wsSaveState === 'error' && (
            <AlertCircle className="w-3.5 h-3.5 text-red-400" />
          )}
          {wsSaveState === 'idle' && (
            <LayoutDashboard className="w-3.5 h-3.5" />
          )}
          {wsSaveState === 'saved' ? 'Saved' : wsSaveState === 'error' ? 'Failed' : 'Save to Workspace'}
        </button>
      )}
      {savedWorkflowId && (
        <a
          href={`/dashboard/workflows?workflow=${savedWorkflowId}`}
          className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          Open in Workspace
        </a>
      )}
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

  // Trend & Cultural Insights sections
  const trendReport = data.trend_report as Record<string, unknown> | undefined;
  if (trendReport?.executive_summary) {
    lines.push('TREND EXECUTIVE SUMMARY', '-'.repeat(40), trendReport.executive_summary as string, '');
  }

  const scoredTrends = data.scored_trends as Array<Record<string, unknown>> | undefined;
  if (scoredTrends && scoredTrends.length > 0) {
    lines.push(`TREND SCORECARD (${scoredTrends.length})`, '-'.repeat(40));
    for (const t of scoredTrends) {
      lines.push(`- ${t.topic} [Score: ${t.relevance_score}] (${t.recommendation})`);
      if (t.rationale) lines.push(`  ${t.rationale}`);
    }
    lines.push('');
  }

  const opportunityAlerts = data.opportunity_alerts as Array<Record<string, unknown>> | undefined;
  if (opportunityAlerts && opportunityAlerts.length > 0) {
    lines.push(`OPPORTUNITY ALERTS (${opportunityAlerts.length})`, '-'.repeat(40));
    for (const a of opportunityAlerts) {
      lines.push(`- [${(a.urgency as string || '').toUpperCase()}] ${a.trend_slug}: ${a.recommendation}`);
    }
    lines.push('');
  }

  const culturalShifts = data.cultural_shifts as Array<Record<string, unknown>> | undefined;
  if (culturalShifts && culturalShifts.length > 0) {
    lines.push(`CULTURAL SHIFTS (${culturalShifts.length})`, '-'.repeat(40));
    for (const s of culturalShifts) {
      lines.push(`- ${s.domain}: ${s.shift_description}`);
    }
    lines.push('');
  }

  // Voice of Customer sections
  const vocHealthScore = data.voc_health_score as number | undefined;
  if (vocHealthScore != null) {
    const mode = data.operating_mode as string | undefined;
    lines.push(`VOC HEALTH SCORE: ${vocHealthScore}/100${mode ? ` (${mode})` : ''}`, '');
  }

  const vocSentiment = data.sentiment as Record<string, unknown> | undefined;
  if (vocSentiment?.overall_sentiment) {
    const overall = vocSentiment.overall_sentiment as Record<string, number>;
    lines.push('SENTIMENT ANALYSIS', '-'.repeat(40));
    lines.push(`Positive: ${((overall.positive ?? 0) * 100).toFixed(0)}%`);
    lines.push(`Neutral: ${((overall.neutral ?? 0) * 100).toFixed(0)}%`);
    lines.push(`Negative: ${((overall.negative ?? 0) * 100).toFixed(0)}%`);
    lines.push('');
  }

  const vocThemes = data.themes as Record<string, unknown> | undefined;
  if (vocThemes) {
    const clusters = (vocThemes.themes ?? []) as Array<Record<string, unknown>>;
    if (clusters.length > 0) {
      lines.push(`THEME CLUSTERS (${clusters.length})`, '-'.repeat(40));
      for (const t of clusters) {
        lines.push(`- ${t.theme_name ?? t.theme_slug}: ${t.feedback_count ?? 0} mentions (severity: ${t.severity_score ?? 'N/A'})`);
      }
      lines.push('');
    }
  }

  const vocNps = data.nps_analysis as Record<string, unknown> | undefined;
  if (vocNps) {
    const current = (vocNps.current_nps ?? vocNps.proxy_nps) as Record<string, number> | undefined;
    if (current) {
      const label = vocNps.nps_available ? 'NPS' : 'PROXY NPS';
      lines.push(`${label} ANALYSIS`, '-'.repeat(40));
      lines.push(`Score: ${current.nps_score ?? 'N/A'}`);
      lines.push(`Promoters: ${current.promoters ?? 0} | Passives: ${current.passives ?? 0} | Detractors: ${current.detractors ?? 0}`);
      lines.push('');
    }
  }

  const vocPainPoints = data.pain_point_priority_matrix as Record<string, unknown> | undefined;
  if (vocPainPoints) {
    const pps = (vocPainPoints.pain_points ?? []) as Array<Record<string, unknown>>;
    if (pps.length > 0) {
      lines.push(`PAIN POINTS (${pps.length})`, '-'.repeat(40));
      for (const pp of pps) {
        lines.push(`- ${pp.name} (severity: ${pp.severity}, frequency: ${pp.frequency})`);
        if (pp.recommended_action) lines.push(`  Action: ${pp.recommended_action}`);
      }
      lines.push('');
    }
  }

  const vocStrategy = data.strategy_bridge as Record<string, unknown> | undefined;
  if (vocStrategy?.executive_summary) {
    lines.push('VOC STRATEGY BRIDGE', '-'.repeat(40), vocStrategy.executive_summary as string, '');
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
    const skip = new Set(['node_results', 'ui_schema', 'score', 'awareness', 'sentiment', 'financials', 'valuation', 'market_overview', 'market_sizing', 'competitive_landscape', 'industry_trends', 'economic_indicators', 'sources', 'confidence_score', 'methodology_notes', 'trend_report', 'scored_trends', 'trend_persona_matrix', 'opportunity_alerts', 'viral_patterns', 'cultural_shifts', 'generational_insights', 'language_trends', 'report_url', 'voc_health_score', 'voc_health_breakdown', 'themes', 'nps_analysis', 'pain_point_priority_matrix', 'strategy_bridge', 'operating_mode', 'data_coverage_score', 'odoo_onboarding_recommendation']);
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
  persona_label?: string;
  total_estimated_cycle_days?: number;
  stages?: JourneyStageFE[];
}

/* ── Trend & Cultural Insights Types ──────────────────────────── */

interface ScoredTrendFE {
  trend_slug?: string;
  topic: string;
  relevance_score: number;
  audience_alignment?: number;
  competitive_landscape?: number;
  brand_fit?: number;
  momentum?: number;
  recommendation?: 'capitalize' | 'monitor' | 'avoid';
  rationale?: string;
  citations?: string[];
  platforms?: string[];
}

interface TrendPersonaMappingFE {
  trend_slug: string;
  persona_slug: string;
  affinity_score: number;
  content_angles?: string[];
  recommended_channels?: string[];
}

interface OpportunityAlertFE {
  alert_id?: string;
  trend_slug: string;
  relevance_score: number;
  urgency: 'immediate' | 'this_week' | 'this_month';
  recommendation: string;
  affected_personas?: string[];
  suggested_response?: string;
  expiry_estimate?: string;
}

interface CulturalShiftFE {
  domain: string;
  shift_description: string;
  evidence_strength?: number;
  affected_demographics?: string[];
  timeline_estimate?: string;
}

interface GenerationalProfileFE {
  generation: string;
  emerging_behaviors?: string[];
  language_patterns?: string[];
  platform_shifts?: string[];
  brand_expectations?: string[];
  subcultures?: string[];
}

interface SlangTermFE {
  term: string;
  definition: string;
  origin_platform?: string;
  adoption_stage?: string;
  sensitivity_flag?: boolean;
}

interface LanguageTrendProfileFE {
  emerging_terms?: SlangTermFE[];
  fading_terms?: string[];
  language_shifts?: string[];
}

interface ViralPatternProfileFE {
  top_formats?: string[];
  emotional_triggers?: string[];
  amplification_mechanics?: string[];
  brand_safe_patterns?: string[];
  brand_unsafe_patterns?: string[];
}

interface TrendReportFE {
  executive_summary?: string;
  trend_scorecard?: ScoredTrendFE[];
  new_trends?: string[];
  rising_trends?: string[];
  fading_trends?: string[];
  competitive_trend_gaps?: string[];
  strategic_recommendations?: string[];
  confidence_score?: number;
}

/* ── TrendCulturalSection ────────────────────────────────────────── */

function TrendCulturalSection({
  trendReport,
  scoredTrends,
  trendPersonaMatrix,
  opportunityAlerts,
  viralPatterns,
  culturalShifts,
  generationalInsights,
  languageTrends,
  sources,
  confidenceScore,
  findings,
  recommendations,
}: {
  trendReport?: TrendReportFE;
  scoredTrends?: ScoredTrendFE[];
  trendPersonaMatrix?: { mappings: TrendPersonaMappingFE[] };
  opportunityAlerts?: OpportunityAlertFE[];
  viralPatterns?: ViralPatternProfileFE;
  culturalShifts?: CulturalShiftFE[];
  generationalInsights?: GenerationalProfileFE[];
  languageTrends?: LanguageTrendProfileFE;
  sources?: SourceEntry[];
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  const [expandedTrend, setExpandedTrend] = useState<string | null>(null);
  const [expandedGen, setExpandedGen] = useState<string | null>(null);

  const execSummary = trendReport?.executive_summary;
  const trendScorecard = scoredTrends ?? trendReport?.trend_scorecard ?? [];
  const stratRecs = trendReport?.strategic_recommendations ?? recommendations ?? [];

  function scoreBadgeColor(score: number) {
    if (score >= 75) return 'text-green-400 bg-green-400/10 border-green-400/30';
    if (score >= 50) return 'text-amber-400 bg-amber-400/10 border-amber-400/30';
    return 'text-red-400 bg-red-400/10 border-red-400/30';
  }

  function recBadge(rec?: string) {
    if (rec === 'capitalize') return { text: 'Capitalize', cls: 'bg-green-400/20 text-green-400' };
    if (rec === 'monitor') return { text: 'Monitor', cls: 'bg-amber-400/20 text-amber-400' };
    if (rec === 'avoid') return { text: 'Avoid', cls: 'bg-red-400/20 text-red-400' };
    return { text: rec ?? '', cls: 'bg-white/10 text-brand-silver' };
  }

  function urgencyStyle(urgency: string) {
    if (urgency === 'immediate') return 'border-red-400/50 bg-red-400/5';
    if (urgency === 'this_week') return 'border-amber-400/50 bg-amber-400/5';
    return 'border-blue-400/50 bg-blue-400/5';
  }

  function urgencyBadge(urgency: string) {
    if (urgency === 'immediate') return { text: 'Immediate', cls: 'bg-red-400/20 text-red-400' };
    if (urgency === 'this_week') return { text: 'This Week', cls: 'bg-amber-400/20 text-amber-400' };
    return { text: 'This Month', cls: 'bg-blue-400/20 text-blue-400' };
  }

  return (
    <div className="space-y-6">
      {/* Confidence Score */}
      {confidenceScore != null && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
            Confidence
          </span>
          <span className="inline-flex items-center rounded-full bg-brand-electric/20 px-3 py-1 text-sm font-bold text-brand-electric">
            {typeof confidenceScore === 'number' ? `${Math.round(confidenceScore * 100)}%` : confidenceScore}
          </span>
        </div>
      )}

      {/* Executive Summary */}
      {execSummary && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Executive Summary
          </h4>
          <div className="bg-white/5 rounded-lg p-4 border border-white/10">
            <MarkdownMessage content={execSummary} />
          </div>
        </section>
      )}

      {/* Opportunity Alerts */}
      {opportunityAlerts && opportunityAlerts.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-400" />
            Opportunity Alerts ({opportunityAlerts.length})
          </h4>
          <div className="space-y-3">
            {opportunityAlerts.map((alert, i) => {
              const ub = urgencyBadge(alert.urgency);
              return (
                <div key={alert.alert_id ?? i} className={`rounded-lg p-4 border ${urgencyStyle(alert.urgency)}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold text-white">
                      {alert.trend_slug?.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ub.cls}`}>{ub.text}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-bold border ${scoreBadgeColor(alert.relevance_score)}`}>
                        {alert.relevance_score}
                      </span>
                    </div>
                  </div>
                  <p className="text-sm text-brand-silver/80 mb-2">{alert.recommendation}</p>
                  {alert.suggested_response && (
                    <p className="text-xs text-brand-silver/60 italic">{alert.suggested_response}</p>
                  )}
                  {alert.affected_personas && alert.affected_personas.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {alert.affected_personas.map((p) => (
                        <span key={p} className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-brand-silver/70">
                          {p}
                        </span>
                      ))}
                    </div>
                  )}
                  {alert.expiry_estimate && (
                    <p className="text-xs text-brand-silver/50 mt-1">Estimated window: {alert.expiry_estimate}</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Trend Scorecard */}
      {trendScorecard.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Trend Scorecard ({trendScorecard.length})
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {trendScorecard.map((trend, i) => {
              const rb = recBadge(trend.recommendation);
              const key = trend.trend_slug ?? `trend-${i}`;
              const isExpanded = expandedTrend === key;
              return (
                <div
                  key={key}
                  className="bg-white/5 rounded-lg p-4 border border-white/10 cursor-pointer hover:border-white/20 transition-colors"
                  onClick={() => setExpandedTrend(isExpanded ? null : key)}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold text-white truncate mr-2">{trend.topic}</span>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${rb.cls}`}>{rb.text}</span>
                      <span className={`text-sm font-bold px-2 py-0.5 rounded-full border ${scoreBadgeColor(trend.relevance_score)}`}>
                        {trend.relevance_score}
                      </span>
                    </div>
                  </div>

                  {/* 4-dimension breakdown bars */}
                  <div className="grid grid-cols-4 gap-1 mb-2">
                    {([
                      ['Audience', trend.audience_alignment],
                      ['Competitive', trend.competitive_landscape],
                      ['Brand Fit', trend.brand_fit],
                      ['Momentum', trend.momentum],
                    ] as [string, number | undefined][]).map(([label, val]) => (
                      <div key={label} className="text-center">
                        <div className="text-[10px] text-brand-silver/50 mb-0.5">{label}</div>
                        <div className="w-full bg-white/10 rounded-full h-1.5">
                          <div
                            className="bg-brand-electric rounded-full h-1.5 transition-all"
                            style={{ width: `${((val ?? 0) / 25) * 100}%` }}
                          />
                        </div>
                        <div className="text-[10px] text-brand-silver/60 mt-0.5">{val ?? 0}/25</div>
                      </div>
                    ))}
                  </div>

                  {/* Platform tags */}
                  {trend.platforms && trend.platforms.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-2">
                      {trend.platforms.map((p) => (
                        <span key={p} className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-brand-silver/60">
                          {p}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-white/10 space-y-2">
                      {trend.rationale && (
                        <p className="text-xs text-brand-silver/70">{trend.rationale}</p>
                      )}
                      {trend.citations && trend.citations.length > 0 && (
                        <div className="space-y-1">
                          <span className="text-[10px] text-brand-silver/50 uppercase">Sources</span>
                          {trend.citations.map((c, ci) => (
                            <a
                              key={ci}
                              href={c}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block text-xs text-brand-electric/80 hover:text-brand-electric truncate"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {c}
                            </a>
                          ))}
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

      {/* Trend-Persona Matrix */}
      {trendPersonaMatrix && trendPersonaMatrix.mappings && trendPersonaMatrix.mappings.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Trend-Persona Matrix
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-brand-silver/50 border-b border-white/10">
                  <th className="text-left py-2 px-3">Trend</th>
                  <th className="text-left py-2 px-3">Persona</th>
                  <th className="text-center py-2 px-3">Affinity</th>
                  <th className="text-left py-2 px-3">Content Angles</th>
                  <th className="text-left py-2 px-3">Channels</th>
                </tr>
              </thead>
              <tbody>
                {trendPersonaMatrix.mappings.map((m, i) => (
                  <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white">
                      {m.trend_slug?.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                    </td>
                    <td className="py-2 px-3 text-brand-silver/80">
                      {m.persona_slug?.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className={`font-bold ${m.affinity_score >= 0.7 ? 'text-green-400' : m.affinity_score >= 0.4 ? 'text-amber-400' : 'text-red-400'}`}>
                        {Math.round(m.affinity_score * 100)}%
                      </span>
                    </td>
                    <td className="py-2 px-3 text-brand-silver/70">
                      {m.content_angles?.slice(0, 2).join(', ')}
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex flex-wrap gap-1">
                        {m.recommended_channels?.slice(0, 3).map((ch) => (
                          <span key={ch} className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-brand-silver/60">
                            {ch}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Cultural Shifts */}
      {culturalShifts && culturalShifts.length > 0 && (() => {
        // Aggressively filter raw web-scrape content, word lists, and duplicates
        const seen = new Set<string>();
        const cleaned = culturalShifts.filter((s) => {
          const desc = (s.shift_description ?? '').trim();
          // Too short or too long to be a real synthesized insight
          if (desc.length < 40 || desc.length > 600) return false;
          // Word/number list (many commas relative to text length)
          const commaRatio = (desc.match(/,/g)?.length ?? 0) / desc.length;
          if (commaRatio > 0.06) return false;
          // Numbered word lists (e.g. "word 2533 word 2534")
          if (/\b\w+\s+\d{3,}\s+\w+\s+\d{3,}/.test(desc)) return false;
          // JSON or structured data patterns
          if (/"\w+":\s*\d{3,}/.test(desc)) return false;
          if (/\b\d{4,}\b.*\b\d{4,}\b.*\b\d{4,}\b/.test(desc)) return false;
          // Error/permission page content
          if (/Oops!|do not have permission|cannot find what|something went wrong|Further Information|Get intouch/i.test(desc)) return false;
          // Uppercase word lists (dictionary-like)
          if ((desc.match(/\b[A-Z]{3,}\b/g)?.length ?? 0) > 6) return false;
          // Raw web scrape indicators: markdown headers, bullet-heavy content, checkmarks
          if ((desc.match(/^#{1,5}\s/gm)?.length ?? 0) >= 2) return false;
          if ((desc.match(/^✅/gm)?.length ?? 0) >= 2) return false;
          // Article/listicle patterns ("### 1.", "## Key", "#### Top")
          if (/^#{2,}\s+\d+\.|^#{2,}\s+(Key|Top|Our|Looking|Further|Conclusion)/m.test(desc)) return false;
          // Promotional / scraped marketing content
          if (/^PROMOTED\b/i.test(desc)) return false;
          // Academic citation fragments
          if (/\(\d{4}\)\s*(stated|found|argued|noted)/i.test(desc)) return false;
          if (/et al\.,?\s*\d{4}/.test(desc)) return false;
          // Footer/nav junk (multiple "[...]" or "Get Report")
          if ((desc.match(/\[\.\.\.\]/g)?.length ?? 0) >= 2) return false;
          if (/^Get Report\b/i.test(desc)) return false;
          // Sentence quality: a real insight should have coherent sentences.
          // Reject if it has < 3 sentences (periods followed by space/end)
          const sentenceCount = desc.split(/[.!?]\s+/).length;
          if (sentenceCount < 2) return false;
          // Content-based dedup (ignore domain — same text = same entry)
          const contentKey = desc.slice(0, 120).toLowerCase().replace(/\s+/g, ' ');
          if (seen.has(contentKey)) return false;
          seen.add(contentKey);
          return true;
        });
        if (cleaned.length === 0) return null;
        return (
          <section>
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
              Cultural Shifts ({cleaned.length})
            </h4>
            <div className="space-y-3">
              {cleaned.map((shift, i) => (
                <div key={i} className="bg-white/5 rounded-lg p-4 border border-white/10">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-semibold text-white capitalize">{shift.domain}</span>
                    {shift.evidence_strength != null && (
                      <span className="text-xs text-brand-silver/50">
                        Evidence: {Math.round(shift.evidence_strength * 100)}%
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-brand-silver/80">
                    {shift.shift_description.length > 400
                      ? shift.shift_description.slice(0, 400) + '…'
                      : shift.shift_description}
                  </p>
                  {shift.affected_demographics && shift.affected_demographics.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {shift.affected_demographics.map((d) => (
                        <span key={d} className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-brand-silver/60">
                          {d}
                        </span>
                      ))}
                    </div>
                  )}
                  {shift.timeline_estimate && (
                    <p className="text-xs text-brand-silver/50 mt-1">Timeline: {shift.timeline_estimate}</p>
                  )}
                </div>
              ))}
            </div>
          </section>
        );
      })()}

      {/* Viral Patterns */}
      {viralPatterns && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Viral Content Patterns
          </h4>
          <div className="bg-white/5 rounded-lg p-4 border border-white/10 space-y-3">
            {viralPatterns.top_formats && viralPatterns.top_formats.length > 0 && (
              <div>
                <span className="text-[10px] text-brand-silver/50 uppercase">Top Formats</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {viralPatterns.top_formats.map((f) => (
                    <span key={f} className="text-xs px-2 py-0.5 rounded-full bg-brand-electric/10 text-brand-electric/80">
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {viralPatterns.emotional_triggers && viralPatterns.emotional_triggers.length > 0 && (
              <div>
                <span className="text-[10px] text-brand-silver/50 uppercase">Emotional Triggers</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {viralPatterns.emotional_triggers.map((t) => (
                    <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-amber-400/10 text-amber-400/80">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {viralPatterns.brand_safe_patterns && viralPatterns.brand_safe_patterns.length > 0 && (
              <div>
                <span className="text-[10px] text-brand-silver/50 uppercase">Brand-Safe Patterns</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {viralPatterns.brand_safe_patterns.map((p) => (
                    <span key={p} className="text-xs px-2 py-0.5 rounded-full bg-green-400/10 text-green-400/80">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {viralPatterns.brand_unsafe_patterns && viralPatterns.brand_unsafe_patterns.length > 0 && (
              <div>
                <span className="text-[10px] text-brand-silver/50 uppercase">Brand-Unsafe Patterns</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {viralPatterns.brand_unsafe_patterns.map((p) => (
                    <span key={p} className="text-xs px-2 py-0.5 rounded-full bg-red-400/10 text-red-400/80">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Generational Insights */}
      {generationalInsights && generationalInsights.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Generational Insights ({generationalInsights.length})
          </h4>
          <div className="space-y-2">
            {generationalInsights.map((gen, i) => {
              const key = gen.generation ?? `gen-${i}`;
              const isOpen = expandedGen === key;
              return (
                <div
                  key={key}
                  className="bg-white/5 rounded-lg border border-white/10 overflow-hidden"
                >
                  <button
                    className="w-full flex items-center justify-between p-3 hover:bg-white/5 transition-colors text-left"
                    onClick={() => setExpandedGen(isOpen ? null : key)}
                  >
                    <span className="text-sm font-semibold text-white capitalize">{gen.generation?.replace(/_/g, ' ')}</span>
                    <span className="text-brand-silver/50 text-xs">{isOpen ? '▲' : '▼'}</span>
                  </button>
                  {isOpen && (
                    <div className="px-3 pb-3 space-y-2">
                      {gen.emerging_behaviors && gen.emerging_behaviors.length > 0 && (
                        <div>
                          <span className="text-[10px] text-brand-silver/50 uppercase">Behaviors</span>
                          <ul className="list-disc list-inside text-xs text-brand-silver/70 mt-0.5">
                            {gen.emerging_behaviors.map((b, bi) => <li key={bi}>{b}</li>)}
                          </ul>
                        </div>
                      )}
                      {gen.platform_shifts && gen.platform_shifts.length > 0 && (
                        <div>
                          <span className="text-[10px] text-brand-silver/50 uppercase">Platform Shifts</span>
                          <ul className="list-disc list-inside text-xs text-brand-silver/70 mt-0.5">
                            {gen.platform_shifts.map((p, pi) => <li key={pi}>{p}</li>)}
                          </ul>
                        </div>
                      )}
                      {gen.brand_expectations && gen.brand_expectations.length > 0 && (
                        <div>
                          <span className="text-[10px] text-brand-silver/50 uppercase">Brand Expectations</span>
                          <ul className="list-disc list-inside text-xs text-brand-silver/70 mt-0.5">
                            {gen.brand_expectations.map((e, ei) => <li key={ei}>{e}</li>)}
                          </ul>
                        </div>
                      )}
                      {gen.language_patterns && gen.language_patterns.length > 0 && (
                        <div>
                          <span className="text-[10px] text-brand-silver/50 uppercase">Language</span>
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {gen.language_patterns.map((l) => (
                              <span key={l} className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-brand-silver/60">{l}</span>
                            ))}
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

      {/* Language Trends */}
      {languageTrends && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Language Trends
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Emerging Terms */}
            {languageTrends.emerging_terms && languageTrends.emerging_terms.length > 0 && (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <h5 className="text-xs font-semibold text-green-400/80 uppercase mb-2">Emerging Terms</h5>
                <div className="space-y-2">
                  {languageTrends.emerging_terms.map((term, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-sm font-medium text-white shrink-0">
                        {term.term}
                        {term.sensitivity_flag && (
                          <span className="ml-1 text-[10px] px-1 py-0.5 rounded bg-red-400/20 text-red-400">sensitive</span>
                        )}
                      </span>
                      <span className="text-xs text-brand-silver/60">{term.definition}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* Fading Terms */}
            {languageTrends.fading_terms && languageTrends.fading_terms.length > 0 && (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <h5 className="text-xs font-semibold text-red-400/80 uppercase mb-2">Fading Terms</h5>
                <div className="flex flex-wrap gap-1">
                  {languageTrends.fading_terms.map((t) => (
                    <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-red-400/10 text-red-400/60 line-through">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* New / Rising / Fading Trends Summary */}
      {trendReport && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {trendReport.new_trends && trendReport.new_trends.length > 0 && (
            <div className="bg-white/5 rounded-lg p-3 border border-white/10">
              <h5 className="text-[10px] text-brand-silver/50 uppercase mb-1">New Trends</h5>
              <ul className="text-xs text-brand-silver/70 space-y-0.5">
                {trendReport.new_trends.map((t, i) => <li key={i}>+ {t}</li>)}
              </ul>
            </div>
          )}
          {trendReport.rising_trends && trendReport.rising_trends.length > 0 && (
            <div className="bg-white/5 rounded-lg p-3 border border-white/10">
              <h5 className="text-[10px] text-green-400/60 uppercase mb-1">Rising Trends</h5>
              <ul className="text-xs text-green-400/70 space-y-0.5">
                {trendReport.rising_trends.map((t, i) => <li key={i}>↑ {t}</li>)}
              </ul>
            </div>
          )}
          {trendReport.fading_trends && trendReport.fading_trends.length > 0 && (
            <div className="bg-white/5 rounded-lg p-3 border border-white/10">
              <h5 className="text-[10px] text-red-400/60 uppercase mb-1">Fading Trends</h5>
              <ul className="text-xs text-red-400/70 space-y-0.5">
                {trendReport.fading_trends.map((t, i) => <li key={i}>↓ {t}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Strategic Recommendations */}
      {stratRecs.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Strategic Recommendations
          </h4>
          {stratRecs.map((r, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={typeof r === 'string' ? r : JSON.stringify(r)} />
            </div>
          ))}
        </section>
      )}

      {/* Findings */}
      {findings && findings.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Key Findings
          </h4>
          {findings.map((f, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={f} />
            </div>
          ))}
        </section>
      )}

      {/* Sources */}
      {sources && sources.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Sources ({sources.length})
          </h4>
          <div className="space-y-1 max-h-60 overflow-y-auto rounded-lg border border-white/5 p-2">
            {sources.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <ExternalLink className="w-3 h-3 text-brand-silver/40 shrink-0" />
                {s.url ? (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-electric/80 hover:text-brand-electric truncate"
                  >
                    {s.title || s.url}
                  </a>
                ) : (
                  <span className="text-brand-silver/60">{s.title || '-'}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

/** Safely render any value for display in persona grids. */
function displayValue(val: unknown): string {
  if (val == null) return '';
  if (typeof val === 'string') return val;
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  if (Array.isArray(val)) {
    return val.map((item) => {
      if (typeof item === 'string') return item;
      if (typeof item === 'object' && item != null) {
        // Extract meaningful text from objects like {name: "X", description: "Y"}
        const obj = item as Record<string, unknown>;
        return obj.name || obj.label || obj.title || obj.description || obj.text || obj.value || JSON.stringify(obj);
      }
      return String(item);
    }).join(', ');
  }
  if (typeof val === 'object') {
    // For nested objects, render as "key: value" pairs
    const obj = val as Record<string, unknown>;
    return Object.entries(obj)
      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
      .join('; ');
  }
  return String(val);
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
  personas: rawPersonas,
  journeyMaps: rawJourneyMaps,
  segmentMatrix: rawSegmentMatrix,
  sources: rawSources,
  confidenceScore,
  findings: rawFindings,
  recommendations: rawRecommendations,
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
  // Defensive: ensure arrays are actually arrays and contain objects (LLM data can be malformed)
  const personas = Array.isArray(rawPersonas) ? rawPersonas.filter((p): p is PersonaProfileFE => p != null && typeof p === 'object' && !Array.isArray(p)) : undefined;
  const journeyMaps = Array.isArray(rawJourneyMaps) ? rawJourneyMaps.filter((j): j is BuyingJourneyMapFE => j != null && typeof j === 'object' && !Array.isArray(j)) : undefined;
  const segmentMatrix = rawSegmentMatrix && typeof rawSegmentMatrix === 'object' && !Array.isArray(rawSegmentMatrix) ? rawSegmentMatrix : undefined;
  const sources = Array.isArray(rawSources) ? rawSources : undefined;
  const findings = Array.isArray(rawFindings) ? rawFindings : undefined;
  const recommendations = Array.isArray(rawRecommendations) ? rawRecommendations : undefined;

  // Helper: coerce any value to an array — prevents .map() crash on strings/objects/null
  const safeArr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
  // Helper: coerce to Record — prevents Object.entries() crash on non-objects
  const safeObj = (v: unknown): Record<string, unknown> =>
    v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};

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
      {executiveSummary && typeof executiveSummary === 'string' && (
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
                  {safeArr(persona.pain_points).length > 0 && (
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Pain Points</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {safeArr(persona.pain_points).slice(0, isExpanded ? undefined : 3).map((pp, i) => (
                          <span key={i} className="rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] text-red-400">
                            {displayValue(pp)}
                          </span>
                        ))}
                        {!isExpanded && safeArr(persona.pain_points).length > 3 && (
                          <span className="text-[11px] text-brand-silver/40">+{safeArr(persona.pain_points).length - 3} more</span>
                        )}
                      </div>
                    </div>
                  )}

                  {safeArr(persona.motivations).length > 0 && (
                    <div>
                      <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Motivations</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {safeArr(persona.motivations).slice(0, isExpanded ? undefined : 3).map((m, i) => (
                          <span key={i} className="rounded-full bg-green-500/10 px-2 py-0.5 text-[11px] text-green-400">
                            {displayValue(m)}
                          </span>
                        ))}
                        {!isExpanded && safeArr(persona.motivations).length > 3 && (
                          <span className="text-[11px] text-brand-silver/40">+{safeArr(persona.motivations).length - 3} more</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Expanded Content */}
                  {isExpanded && (
                    <div className="space-y-3 pt-2 border-t border-white/5">
                      {/* Demographics Grid */}
                      {Object.keys(safeObj(persona.demographics)).length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Demographics</span>
                          <div className="grid grid-cols-2 gap-2 mt-1">
                            {Object.entries(safeObj(persona.demographics)).map(([key, val]) => (
                              <div key={key} className="text-[11px]">
                                <span className="text-brand-silver/50 capitalize">{key.replace(/_/g, ' ')}: </span>
                                <span className="text-brand-silver">{displayValue(val)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Psychographics */}
                      {Object.keys(safeObj(persona.psychographics)).length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Psychographics</span>
                          <div className="grid grid-cols-2 gap-2 mt-1">
                            {Object.entries(safeObj(persona.psychographics)).map(([key, val]) => (
                              <div key={key} className="text-[11px]">
                                <span className="text-brand-silver/50 capitalize">{key.replace(/_/g, ' ')}: </span>
                                <span className="text-brand-silver">{displayValue(val)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Objections */}
                      {safeArr(persona.objections).length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Objections</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {safeArr(persona.objections).map((o, i) => (
                              <span key={i} className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-400">
                                {displayValue(o)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Preferred Channels */}
                      {safeArr(persona.preferred_channels).length > 0 && (
                        <div>
                          <span className="text-[10px] uppercase tracking-wider text-brand-silver/40">Preferred Channels</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {safeArr(persona.preferred_channels).map((ch, i) => (
                              <span key={i} className="rounded-full bg-brand-electric/10 px-2 py-0.5 text-[11px] text-brand-electric">
                                {displayValue(ch)}
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
              // Resolve label: prefer persona_label, fall back to matching
              // persona's segment_label, then slugify persona_slug
              const journeyLabel =
                journey.persona_label ||
                personas?.find((p) => p.slug === journey.persona_slug)?.segment_label ||
                journey.persona_slug?.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) ||
                `Persona ${idx + 1}`;

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
                      {journeyLabel}
                    </h6>
                    {journey.total_estimated_cycle_days != null && (
                      <span className="text-xs text-brand-silver/50">
                        ~{journey.total_estimated_cycle_days} days
                      </span>
                    )}
                  </div>

                  {/* Stage Timeline */}
                  <div className="flex items-center gap-1 overflow-x-auto">
                    {safeArr(journey.stages).map((rawStage, si) => {
                      const stage = safeObj(rawStage) as unknown as JourneyStageFE;
                      return (
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
                        {si < safeArr(journey.stages).length - 1 && (
                          <div className="w-4 h-px bg-white/20 mx-0.5" />
                        )}
                      </div>
                      );
                    })}
                  </div>

                  {/* Expanded Stage Details */}
                  {isJExpanded && (
                    <div className="space-y-3 pt-2 border-t border-white/5">
                      {safeArr(journey.stages).map((rawStage, si) => {
                        const stage = safeObj(rawStage) as unknown as JourneyStageFE;
                        return (
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
                            {safeArr(stage.touchpoints).length > 0 && (
                              <div>
                                <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Touchpoints</span>
                                <ul className="mt-0.5 space-y-0.5">
                                  {safeArr(stage.touchpoints).map((tp, ti) => (
                                    <li key={ti} className="text-[10px] text-brand-silver/60">• {displayValue(tp)}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {safeArr(stage.info_needs).length > 0 && (
                              <div>
                                <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Info Needs</span>
                                <ul className="mt-0.5 space-y-0.5">
                                  {safeArr(stage.info_needs).map((need, ni) => (
                                    <li key={ni} className="text-[10px] text-brand-silver/60">• {displayValue(need)}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {safeArr(stage.decision_criteria).length > 0 && (
                              <div>
                                <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Decision Criteria</span>
                                <ul className="mt-0.5 space-y-0.5">
                                  {safeArr(stage.decision_criteria).map((dc, di) => (
                                    <li key={di} className="text-[10px] text-brand-silver/60">• {displayValue(dc)}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {safeArr(stage.content_recommendations).length > 0 && (
                              <div>
                                <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Content Recs</span>
                                <ul className="mt-0.5 space-y-0.5">
                                  {safeArr(stage.content_recommendations).map((cr, ci) => (
                                    <li key={ci} className="text-[10px] text-brand-silver/60">• {displayValue(cr)}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>

                          {safeArr(stage.objections).length > 0 && (
                            <div>
                              <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Objections at this stage</span>
                              <div className="flex flex-wrap gap-1 mt-0.5">
                                {safeArr(stage.objections).map((obj, oi) => (
                                  <span key={oi} className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-400">{displayValue(obj)}</span>
                                ))}
                              </div>
                            </div>
                          )}

                          {safeArr(stage.key_actions).length > 0 && (
                            <div>
                              <span className="text-[9px] uppercase tracking-wider text-brand-silver/40">Key Actions</span>
                              <ul className="mt-0.5 space-y-0.5">
                                {safeArr(stage.key_actions).map((action, ai) => (
                                  <li key={ai} className="text-[10px] text-brand-silver/60">• {displayValue(action)}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                        ); })}
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
          <div className="overflow-x-auto max-h-60 overflow-y-auto rounded-lg border border-white/5">
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

/* ── VoiceOfCustomerSection ─────────────────────────────────────────── */

interface VoCSentimentFELocal {
  overall_sentiment?: { positive?: number; neutral?: number; negative?: number };
  emotion_profile?: Record<string, number>;
  channel_sentiments?: Array<{
    channel: string;
    provenance?: string;
    sentiment?: { positive?: number; neutral?: number; negative?: number };
    feedback_count?: number;
    confidence?: number;
  }>;
  persona_sentiments?: Record<string, { positive?: number; neutral?: number; negative?: number }>;
  trend_direction?: string;
  data_coverage_score?: number;
}

interface VoCThemeClusterLocal {
  theme_slug?: string;
  theme_name?: string;
  feedback_count?: number;
  severity_score?: number;
  sentiment?: { positive?: number; neutral?: number; negative?: number };
  sub_themes?: Array<{
    name: string;
    feedback_count?: number;
    sentiment?: { positive?: number; neutral?: number; negative?: number };
    representative_quotes?: string[];
  }>;
  representative_quotes?: string[];
  competitor_correlation?: string;
  market_context?: string;
}

interface VoCThemeMapLocal {
  themes?: VoCThemeClusterLocal[];
  total_feedback_analyzed?: number;
}

interface VoCNPSLocal {
  nps_available?: boolean;
  current_nps?: {
    promoters?: number;
    passives?: number;
    detractors?: number;
    nps_score?: number;
    total_responses?: number;
  };
  proxy_nps?: {
    promoters?: number;
    passives?: number;
    detractors?: number;
    nps_score?: number;
    total_responses?: number;
  };
  drivers?: (string | { driver?: string; relevance_note?: string })[];
  detractor_themes?: (string | { theme?: string; explanation?: string })[];
  data_source?: string;
}

interface VoCPainPointLocal {
  name?: string;
  severity?: number;
  frequency?: number;
  persona_impact?: string[];
  competitor_gap?: string;
  trend_alignment?: string;
  recommended_action?: string;
}

interface VoCStrategyBridgeLocal {
  executive_summary?: string;
  voc_health_score?: number;
  voc_health_breakdown?: Record<string, number>;
  operating_mode?: string;
  odoo_onboarding_recommendation?: string;
  cross_agent_insights?: Record<string, string>;
  strategic_recommendations?: string[];
}

/* ── Section Error Fallback ──────────────────────────────────────── */

function SectionErrorFallback({ section }: { section: string }) {
  return (
    <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6 text-center">
      <AlertCircle className="w-8 h-8 text-red-400 mx-auto mb-2" />
      <h4 className="text-sm font-semibold text-white mb-1">
        Could not render {section}
      </h4>
      <p className="text-xs text-brand-silver/60">
        The data for this section could not be displayed. Other sections are unaffected.
      </p>
    </div>
  );
}

/* ── BrandDiscoverySection — tabbed container for WF1 agents ────── */

type BrandDiscoveryTab = 'market_research' | 'competitor_intel' | 'audience_persona' | 'trend_cultural' | 'voice_of_customer';

interface BrandDiscoverySectionProps {
  // Market Research
  hasMarketResearch: boolean;
  marketOverview?: string;
  marketSizing?: Record<string, unknown>;
  competitiveLandscape?: CompetitorEntry[];
  industryTrends?: string[];
  economicIndicators?: Record<string, unknown>;
  // Competitor Intelligence
  hasCompetitorIntelligence: boolean;
  ciaExecutiveSummary?: string;
  competitors?: CIACompetitorProfile[];
  competitorMatrix?: Record<string, Record<string, number>>;
  swotAnalyses?: SWOTAnalysis[];
  positioningGaps?: PositioningGap[];
  benchmarkingReport?: Record<string, unknown>;
  // Audience Persona
  hasAudiencePersona: boolean;
  apaExecutiveSummary?: string;
  personas?: PersonaProfileFE[];
  journeyMaps?: BuyingJourneyMapFE[];
  segmentMatrix?: Record<string, unknown>;
  // Trend & Cultural
  hasTrendCultural: boolean;
  trendReport?: TrendReportFE;
  scoredTrends?: ScoredTrendFE[];
  trendPersonaMatrix?: { mappings: TrendPersonaMappingFE[] };
  opportunityAlerts?: OpportunityAlertFE[];
  viralPatterns?: ViralPatternProfileFE;
  culturalShifts?: CulturalShiftFE[];
  generationalInsights?: GenerationalProfileFE[];
  languageTrends?: LanguageTrendProfileFE;
  // Voice of Customer
  hasVoiceOfCustomer: boolean;
  vocHealthScore?: number;
  operatingMode?: string;
  dataCoverageScore?: number;
  sentiment?: VoCSentimentFELocal;
  themes?: VoCThemeMapLocal;
  npsAnalysis?: VoCNPSLocal;
  painPointMatrix?: { pain_points?: VoCPainPointLocal[]; methodology?: string };
  strategyBridge?: VoCStrategyBridgeLocal;
  // Shared
  sources?: SourceEntry[];
  confidenceScores?: Record<string, number>;
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}

function BrandDiscoverySection(props: BrandDiscoverySectionProps) {
  const tabs: { key: BrandDiscoveryTab; label: string; has: boolean }[] = [
    { key: 'market_research', label: 'Market Research', has: props.hasMarketResearch },
    { key: 'competitor_intel', label: 'Competitor Intel', has: props.hasCompetitorIntelligence },
    { key: 'audience_persona', label: 'Audience Personas', has: props.hasAudiencePersona },
    { key: 'trend_cultural', label: 'Trends & Culture', has: props.hasTrendCultural },
    { key: 'voice_of_customer', label: 'Voice of Customer', has: props.hasVoiceOfCustomer },
  ];

  const availableTabs = tabs.filter((t) => t.has);
  const [activeTab, setActiveTab] = useState<BrandDiscoveryTab>(availableTabs[0]?.key ?? 'market_research');

  const cs = props.confidenceScores ?? {};

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-bold text-white">Brand Discovery Intelligence</h3>

      {/* Tab navigation */}
      <div className="flex gap-1 overflow-x-auto border-b border-white/10 pb-px">
        {availableTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1.5 text-xs font-medium rounded-t-md transition-colors whitespace-nowrap ${activeTab === tab.key ? 'bg-brand-electric/20 text-brand-electric border-b-2 border-brand-electric' : 'text-brand-silver/60 hover:text-white hover:bg-white/5'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'market_research' && props.hasMarketResearch && (
        <ErrorBoundary fallback={<SectionErrorFallback section="Market Research" />}>
          <MarketResearchSection
            marketOverview={props.marketOverview}
            marketSizing={props.marketSizing}
            competitiveLandscape={props.competitiveLandscape}
            industryTrends={props.industryTrends}
            economicIndicators={props.economicIndicators}
            sources={props.sources}
            confidenceScore={cs.market_research ?? props.confidenceScore}
            findings={props.findings}
            recommendations={props.recommendations}
          />
        </ErrorBoundary>
      )}

      {activeTab === 'competitor_intel' && props.hasCompetitorIntelligence && (
        <ErrorBoundary fallback={<SectionErrorFallback section="Competitor Intelligence" />}>
          <CompetitorIntelligenceSection
            executiveSummary={props.ciaExecutiveSummary}
            competitors={props.competitors}
            competitorMatrix={props.competitorMatrix}
            swotAnalyses={props.swotAnalyses}
            positioningGaps={props.positioningGaps}
            benchmarkingReport={props.benchmarkingReport}
            sources={props.sources}
            confidenceScore={cs.competitor_intelligence ?? props.confidenceScore}
            findings={props.findings}
            recommendations={props.recommendations}
          />
        </ErrorBoundary>
      )}

      {activeTab === 'audience_persona' && props.hasAudiencePersona && (
        <ErrorBoundary fallback={<SectionErrorFallback section="Audience Personas" />}>
          <AudiencePersonaSection
            executiveSummary={props.apaExecutiveSummary}
            personas={props.personas}
            journeyMaps={props.journeyMaps}
            segmentMatrix={props.segmentMatrix}
            sources={props.sources}
            confidenceScore={cs.audience_persona ?? props.confidenceScore}
            findings={props.findings}
            recommendations={props.recommendations}
          />
        </ErrorBoundary>
      )}

      {activeTab === 'trend_cultural' && props.hasTrendCultural && (
        <ErrorBoundary fallback={<SectionErrorFallback section="Trends & Culture" />}>
          <TrendCulturalSection
            trendReport={props.trendReport}
            scoredTrends={props.scoredTrends}
            trendPersonaMatrix={props.trendPersonaMatrix}
            opportunityAlerts={props.opportunityAlerts}
            viralPatterns={props.viralPatterns}
            culturalShifts={props.culturalShifts}
            generationalInsights={props.generationalInsights}
            languageTrends={props.languageTrends}
            sources={props.sources}
            confidenceScore={cs.trend_cultural ?? props.confidenceScore}
            findings={props.findings}
            recommendations={props.recommendations}
          />
        </ErrorBoundary>
      )}

      {activeTab === 'voice_of_customer' && props.hasVoiceOfCustomer && (
        <ErrorBoundary fallback={<SectionErrorFallback section="Voice of Customer" />}>
          <VoiceOfCustomerSection
            vocHealthScore={props.vocHealthScore}
            operatingMode={props.operatingMode}
            dataCoverageScore={props.dataCoverageScore}
            sentiment={props.sentiment}
            themes={props.themes}
            npsAnalysis={props.npsAnalysis}
            painPointMatrix={props.painPointMatrix}
            strategyBridge={props.strategyBridge}
            sources={props.sources}
            confidenceScore={cs.voice_of_customer ?? props.confidenceScore}
            findings={props.findings}
            recommendations={props.recommendations}
          />
        </ErrorBoundary>
      )}
    </div>
  );
}

/* ── BrandPositioningDashboard (inline) ──────────────────────────── */

interface BPAPositioningStatement {
  statement?: string;
  framework_used?: string;
  framework_rationale?: string;
  target_audience?: string;
  need?: string;
  category?: string;
  key_benefit?: string;
  reason_to_believe?: string;
  scores?: Record<string, number>;
  data_citations?: string[];
}

interface BPAPerceptualMap {
  map_id?: string;
  dimension_x?: string;
  dimension_y?: string;
  entities?: Array<{ name?: string; x?: number; y?: number; is_brand?: boolean; is_target?: boolean }>;
  migration_vector?: { from_x?: number; from_y?: number; to_x?: number; to_y?: number };
  white_space_highlighted?: Array<Record<string, unknown>>;
  differentiation_potential_score?: number;
  is_primary_recommended?: boolean;
}

interface BPACanvas {
  fit_score?: number;
  fit_analysis?: string;
  customer_profile?: {
    jobs?: string[];
    pains?: string[];
    gains?: string[];
  };
  value_map?: {
    products?: string[];
    pain_relievers?: string[];
    gain_creators?: string[];
  };
}

interface BPADifferentiation {
  pods?: string[];
  pops?: string[];
  rtbs?: string[];
  proof_points?: string[];
  competitive_vulnerabilities?: string[];
  overall_differentiation_score?: number;
}

interface BPAStrategy {
  executive_summary?: string;
  strategic_pillars?: Array<{ name?: string; description?: string }>;
  implementation_timeline?: Array<{ phase?: string; timeframe?: string; actions?: string[] }>;
  success_metrics?: Array<{ metric?: string; target?: string; timeframe?: string }>;
}

// ── Brand Architecture Section ──────────────────────────────────────

interface BAAModelScore {
  model: string;
  positioning_alignment: number;
  audience_fit: number;
  competitive_diff: number;
  operational_efficiency: number;
  total: number;
  rationale: string;
}

interface BAARecommendation {
  recommended_model: string;
  model_scores: BAAModelScore[];
  why_not_others: string[];
  confidence_score: number;
  citations: string[];
}

interface BAAHierarchyNode {
  name: string;
  type: string;
  relationship_to_parent?: string;
  target_persona?: string;
  positioning_score?: number;
  visual_identity_guideline?: string;
  children?: BAAHierarchyNode[];
}

interface BAAHierarchy {
  root: BAAHierarchyNode;
  total_depth: number;
  total_nodes: number;
}

interface BAANamingHierarchy {
  naming_pattern: string;
  naming_rules: Array<{ rule?: string; scope?: string; example?: string }>;
  consistency_score: number;
}

interface BAAGrowthPath {
  phases: Array<{ phase?: string; timeline?: string; actions?: string[]; metrics?: string[] }>;
  portfolio_risk_assessment: Array<{ risk?: string; severity?: string; mitigation?: string }>;
}

function BrandArchitectureSection({
  recommendation,
  hierarchy,
  namingHierarchy,
  growthPath,
  archStrategy,
  confidenceScore,
  sources,
  findings,
  recommendations,
}: {
  recommendation?: BAARecommendation;
  hierarchy?: BAAHierarchy;
  namingHierarchy?: BAANamingHierarchy;
  growthPath?: BAAGrowthPath;
  archStrategy?: Record<string, unknown>;
  confidenceScore?: number;
  sources?: SourceEntry[];
  findings?: string[];
  recommendations?: string[];
}) {
  const [activeTab, setActiveTab] = useState<'model' | 'hierarchy' | 'naming' | 'growth' | 'strategy'>('model');

  function scoreColor(score: number) {
    if (score >= 80) return 'text-green-400';
    if (score >= 60) return 'text-amber-400';
    return 'text-red-400';
  }

  function scoreBg(score: number) {
    if (score >= 80) return 'bg-green-400';
    if (score >= 60) return 'bg-amber-400';
    return 'bg-red-400';
  }

  const tabs = [
    { key: 'model' as const, label: 'Architecture Model' },
    { key: 'hierarchy' as const, label: 'Brand Hierarchy' },
    { key: 'naming' as const, label: 'Naming' },
    { key: 'growth' as const, label: 'Growth Path' },
    { key: 'strategy' as const, label: 'Strategy' },
  ];

  const modelScores = recommendation?.model_scores ?? [];
  const recommended = recommendation?.recommended_model ?? '';
  const recommendedLabel = recommended.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const whyNot = recommendation?.why_not_others ?? [];
  const root = hierarchy?.root;
  const rules = namingHierarchy?.naming_rules ?? [];
  const phases = growthPath?.phases ?? [];
  const risks = growthPath?.portfolio_risk_assessment ?? [];

  // Recursive hierarchy tree renderer
  function renderNode(node: BAAHierarchyNode, depth: number = 0) {
    const typeLabel = (node.type || '').replace(/_/g, ' ');
    const indent = depth * 20;
    return (
      <div key={`${node.name}-${depth}`}>
        <div className="flex items-center gap-2 py-1.5 border-b border-white/5" style={{ paddingLeft: `${indent}px` }}>
          <span className="text-brand-electric text-xs">{depth === 0 ? '◆' : depth === 1 ? '├─' : '└──'}</span>
          <span className="text-sm font-medium text-white">{node.name}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/10 text-brand-silver/70">{typeLabel}</span>
          {node.positioning_score != null && (
            <span className={`text-[10px] font-bold ${scoreColor(node.positioning_score)}`}>{node.positioning_score}</span>
          )}
        </div>
        {node.children?.map(child => renderNode(child, depth + 1))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-bold text-white">Brand Architecture Strategy</h3>
        {confidenceScore != null && (() => {
          const pct = confidenceScore <= 1 ? Math.round(confidenceScore * 100) : Math.round(confidenceScore);
          return (
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold border ${pct >= 70 ? 'text-green-400 bg-green-400/10 border-green-400/30' : pct >= 40 ? 'text-amber-400 bg-amber-400/10 border-amber-400/30' : 'text-red-400 bg-red-400/10 border-red-400/30'}`}>
              Confidence: {pct}%
            </span>
          );
        })()}
      </div>

      {/* Recommended Model Badge */}
      {recommended && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-brand-electric/10 border border-brand-electric/20">
          <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-brand-electric/20 flex items-center justify-center text-brand-electric text-lg">◇</div>
          <div>
            <div className="text-xs text-brand-silver/60 uppercase tracking-wider">Recommended Model</div>
            <div className="text-lg font-bold text-white">{recommendedLabel}</div>
          </div>
        </div>
      )}

      {/* Tab navigation */}
      <div className="flex gap-1 overflow-x-auto border-b border-white/10 pb-px">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1.5 text-xs font-medium rounded-t-md transition-colors whitespace-nowrap ${activeTab === tab.key ? 'bg-brand-electric/20 text-brand-electric border-b-2 border-brand-electric' : 'text-brand-silver/60 hover:text-white hover:bg-white/5'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Model tab */}
      {activeTab === 'model' && (
        <div className="space-y-4">
          {/* Model comparison table */}
          {modelScores.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-brand-silver/60 text-xs uppercase">
                    <th className="text-left py-2 pr-3">Model</th>
                    <th className="text-center py-2 px-2">Positioning</th>
                    <th className="text-center py-2 px-2">Audience</th>
                    <th className="text-center py-2 px-2">Competitive</th>
                    <th className="text-center py-2 px-2">Efficiency</th>
                    <th className="text-center py-2 px-2">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {modelScores
                    .sort((a, b) => (b.total ?? 0) - (a.total ?? 0))
                    .map((ms) => {
                      const modelName = (ms.model || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                      const isRec = ms.model === recommended;
                      return (
                        <tr key={ms.model} className={`border-t border-white/5 ${isRec ? 'bg-brand-electric/5' : ''}`}>
                          <td className="py-2 pr-3">
                            <span className="text-white font-medium">{modelName}</span>
                            {isRec && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-brand-electric/20 text-brand-electric">★ Recommended</span>}
                          </td>
                          <td className={`text-center py-2 px-2 font-bold ${scoreColor((ms.positioning_alignment / 25) * 100)}`}>{ms.positioning_alignment}/25</td>
                          <td className={`text-center py-2 px-2 font-bold ${scoreColor((ms.audience_fit / 25) * 100)}`}>{ms.audience_fit}/25</td>
                          <td className={`text-center py-2 px-2 font-bold ${scoreColor((ms.competitive_diff / 25) * 100)}`}>{ms.competitive_diff}/25</td>
                          <td className={`text-center py-2 px-2 font-bold ${scoreColor((ms.operational_efficiency / 25) * 100)}`}>{ms.operational_efficiency}/25</td>
                          <td className="text-center py-2 px-2">
                            <div className="relative w-full h-2 bg-white/10 rounded-full overflow-hidden">
                              <div className={`absolute left-0 top-0 h-full rounded-full ${scoreBg(ms.total)}`} style={{ width: `${ms.total}%` }} />
                            </div>
                            <span className={`text-xs font-bold ${scoreColor(ms.total)}`}>{ms.total}/100</span>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}

          {/* Why not others */}
          {whyNot.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Why Not Others</h5>
              <ul className="space-y-1">
                {whyNot.map((reason, i) => (
                  <li key={i} className="text-sm text-brand-silver/80 flex items-start gap-2">
                    <span className="text-red-400/60 mt-0.5">✕</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Hierarchy tab */}
      {activeTab === 'hierarchy' && root && (
        <div className="space-y-3">
          <div className="flex gap-4 text-xs text-brand-silver/60">
            <span>Depth: <span className="text-white font-bold">{hierarchy?.total_depth ?? 0}</span></span>
            <span>Entities: <span className="text-white font-bold">{hierarchy?.total_nodes ?? 0}</span></span>
          </div>
          <div className="p-4 rounded-xl bg-white/5 border border-white/10">
            {renderNode(root)}
          </div>
        </div>
      )}

      {/* Naming tab */}
      {activeTab === 'naming' && namingHierarchy && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-brand-silver/60 uppercase">Naming Pattern</div>
              <div className="text-white font-medium">{namingHierarchy.naming_pattern}</div>
            </div>
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold border ${(namingHierarchy.consistency_score ?? 0) >= 70 ? 'text-green-400 bg-green-400/10 border-green-400/30' : 'text-amber-400 bg-amber-400/10 border-amber-400/30'}`}>
              Consistency: {namingHierarchy.consistency_score}/100
            </span>
          </div>
          {rules.length > 0 && (
            <div className="space-y-2">
              {rules.map((rule, i) => (
                <div key={i} className="p-3 rounded-lg bg-white/5 border border-white/10">
                  <div className="text-sm text-white font-medium">{rule.rule || `Rule ${i + 1}`}</div>
                  {rule.scope && <div className="text-xs text-brand-silver/60 mt-0.5">Scope: {rule.scope}</div>}
                  {rule.example && <div className="text-xs text-brand-electric/80 mt-0.5">Example: {rule.example}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Growth tab */}
      {activeTab === 'growth' && (
        <div className="space-y-4">
          {phases.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">Growth Phases</h5>
              <div className="space-y-3">
                {phases.map((phase, i) => (
                  <div key={i} className="p-4 rounded-xl bg-white/5 border border-white/10">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-bold text-white">{phase.phase || `Phase ${i + 1}`}</span>
                      {phase.timeline && <span className="text-xs px-2 py-0.5 rounded-full bg-brand-electric/20 text-brand-electric">{phase.timeline}</span>}
                    </div>
                    {phase.actions && phase.actions.length > 0 && (
                      <ul className="space-y-1 mt-2">
                        {phase.actions.map((action, j) => (
                          <li key={j} className="text-sm text-brand-silver/80 flex items-start gap-2">
                            <span className="text-brand-electric mt-0.5">→</span>
                            <span>{action}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {risks.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">Portfolio Risks</h5>
              <div className="space-y-2">
                {risks.map((risk, i) => (
                  <div key={i} className="p-3 rounded-lg bg-red-400/5 border border-red-400/10">
                    <div className="text-sm font-medium text-white">{risk.risk || `Risk ${i + 1}`}</div>
                    {risk.severity && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-400/20 text-red-400">{risk.severity}</span>}
                    {risk.mitigation && <div className="text-xs text-brand-silver/70 mt-1">Mitigation: {risk.mitigation}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Strategy tab */}
      {activeTab === 'strategy' && (
        <div className="space-y-4">
          {/* Executive Summary */}
          {typeof archStrategy?.executive_summary === 'string' && (
            <div className="glass-card p-4 border border-white/10">
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Executive Summary
              </h4>
              <p className="text-sm text-brand-silver/80 leading-relaxed">{archStrategy.executive_summary}</p>
            </div>
          )}

          {/* Strategic Rationale */}
          {typeof archStrategy?.strategic_rationale === 'string' && (
            <div className="glass-card p-4 border border-white/10">
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Strategic Rationale
              </h4>
              <p className="text-sm text-brand-silver/80 leading-relaxed">{archStrategy.strategic_rationale}</p>
            </div>
          )}

          {/* Competitive Advantages */}
          {(() => {
            const advantages = archStrategy?.competitive_advantages;
            if (!advantages || !Array.isArray(advantages) || advantages.length === 0) return null;
            return (
              <div>
                <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                  Competitive Advantages
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {advantages.map((adv: string, i: number) => (
                    <div key={i} className="glass-card p-3 border border-green-400/10 flex gap-2 items-start">
                      <span className="text-green-400 mt-0.5 shrink-0">✓</span>
                      <span className="text-sm text-brand-silver/80">{typeof adv === 'string' ? adv : JSON.stringify(adv)}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Implementation Priorities */}
          {(() => {
            const priorities = archStrategy?.implementation_priorities;
            if (!priorities || !Array.isArray(priorities) || priorities.length === 0) return null;
            return (
              <div>
                <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                  Implementation Priorities
                </h4>
                <div className="space-y-2">
                  {priorities.map((p: string, i: number) => (
                    <div key={i} className="glass-card p-3 border border-white/10 flex gap-3 items-start">
                      <span className="text-brand-electric font-semibold text-sm shrink-0">{i + 1}.</span>
                      <span className="text-sm text-brand-silver/80">{typeof p === 'string' ? p : JSON.stringify(p)}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Success Metrics */}
          {(() => {
            const metrics = archStrategy?.success_metrics;
            if (!metrics || !Array.isArray(metrics) || metrics.length === 0) return null;
            return (
              <div>
                <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                  Success Metrics
                </h4>
                <div className="space-y-1.5">
                  {metrics.map((m: unknown, i: number) => {
                    if (typeof m === 'string') {
                      return (
                        <div key={i} className="flex gap-2 items-start p-2.5 rounded-lg bg-white/5 border border-white/10">
                          <span className="text-brand-electric shrink-0">◎</span>
                          <span className="text-sm text-brand-silver/80">{m}</span>
                        </div>
                      );
                    }
                    const obj = m as Record<string, string>;
                    return (
                      <div key={i} className="flex gap-2 items-start p-2.5 rounded-lg bg-white/5 border border-white/10">
                        <span className="text-brand-electric shrink-0">◎</span>
                        <div className="text-sm">
                          <span className="text-white">{obj.metric || obj.name || ''}</span>
                          {obj.target && <span className="text-brand-electric ml-2">{obj.target}</span>}
                          {obj.timeframe && <span className="text-brand-silver/50 ml-2">({obj.timeframe})</span>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          {/* Remaining strategy fields (catch-all for any extra keys) */}
          {(() => {
            if (!archStrategy || typeof archStrategy !== 'object') return null;
            const knownStrategyKeys = new Set([
              'executive_summary', 'strategic_rationale', 'competitive_advantages',
              'implementation_priorities', 'success_metrics',
            ]);
            const extraEntries = Object.entries(archStrategy as Record<string, unknown>).filter(
              ([k]) => !knownStrategyKeys.has(k)
            );
            if (extraEntries.length === 0) return null;
            return (
              <div className="space-y-3">
                {extraEntries.map(([key, value]) => (
                  <div key={key} className="glass-card p-3 border border-white/10">
                    <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                      {key.replace(/_/g, ' ')}
                    </h4>
                    {typeof value === 'string' ? (
                      <p className="text-sm text-brand-silver/80 leading-relaxed">{value}</p>
                    ) : Array.isArray(value) ? (
                      <ul className="space-y-1">
                        {(value as unknown[]).map((item, i) => (
                          <li key={i} className="text-sm text-brand-silver/80 flex gap-2 items-start">
                            <span className="text-brand-electric/40 shrink-0">→</span>
                            {typeof item === 'string' ? item : String(JSON.stringify(item))}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-brand-silver/80">{String(JSON.stringify(value, null, 2))}</p>
                    )}
                  </div>
                ))}
              </div>
            );
          })()}

          {/* Key Findings */}
          {findings && findings.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Key Findings</h4>
              <div className="space-y-1.5">
                {findings.filter(f => typeof f === 'string' && f.trim()).map((f, i) => (
                  <div key={i} className="flex gap-2 items-start p-2.5 rounded-lg bg-white/5 border border-white/10">
                    <span className="text-amber-400 shrink-0">●</span>
                    <span className="text-sm text-brand-silver/80">{f}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {recommendations && recommendations.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Recommendations</h4>
              <div className="space-y-1.5">
                {recommendations.filter(r => typeof r === 'string' && r.trim()).map((r, i) => (
                  <div key={i} className="flex gap-2 items-start p-2.5 rounded-lg bg-brand-electric/5 border border-brand-electric/10">
                    <span className="text-brand-electric shrink-0">→</span>
                    <span className="text-sm text-brand-silver/80">{r}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sources */}
          {sources && sources.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Sources</h4>
              <div className="space-y-1">
                {sources.map((s, i) => {
                  const src = typeof s === 'string' ? { title: s } : (s as SourceEntry & Record<string, string>);
                  const title = src.title || src['name'] || src['source'] || src.description || '';
                  const url = src.url || src['link'] || '';
                  const detail = src.description || src.type || src['category'] || '';
                  return (
                    <div key={i} className="flex gap-2 items-start p-2 rounded-lg bg-white/5 border border-white/10">
                      <span className="text-brand-silver/40 text-xs shrink-0 mt-0.5">[{i + 1}]</span>
                      <div className="text-sm">
                        {url ? (
                          <a href={url} target="_blank" rel="noopener noreferrer" className="text-brand-electric hover:underline">
                            {title || url}
                          </a>
                        ) : (
                          <span className="text-white">{title || `Source ${i + 1}`}</span>
                        )}
                        {detail && title !== detail && (
                          <span className="text-brand-silver/50 ml-2 text-xs">— {detail}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
 * Brand Naming & Tagline (NTA) Section — 4 tabs
 * ══════════════════════════════════════════════════════════════════════════ */

interface NTANameScore {
  linguistic?: number;
  memorability?: number;
  availability?: number;
  strategy_alignment?: number;
  overall?: number;
}

interface NTAAvailability {
  domain_com?: boolean | null;
  domain_io?: boolean | null;
  domain_co?: boolean | null;
  twitter?: boolean | null;
  instagram?: boolean | null;
  linkedin?: boolean | null;
  trademark_clear?: boolean | null;
  trademark_notes?: string;
}

interface NTANameCandidate {
  name: string;
  rationale?: string;
  naming_type?: string;
  scores?: NTANameScore;
  availability?: NTAAvailability;
  shortlisted?: boolean;
}

interface NTATagline {
  tagline: string;
  name?: string;
  emotional_appeal?: string;
  memorability_score?: number;
  positioning_alignment?: string;
}

interface NTANamingBrief {
  recommended_name?: string;
  recommended_tagline?: string;
  rationale?: string;
  positioning_alignment?: string;
  personality_alignment?: string;
  architecture_fit?: string;
  next_steps?: string[];
}

/* ══════════════════════════════════════════════════════════════════════════
 * Brand Story & Narrative (BSA) Types
 * ══════════════════════════════════════════════════════════════════════════ */

interface BSAStoryVersion {
  version_label?: string;
  word_count?: number;
  content?: string;
  archetype_arc_alignment?: number;
  emotional_resonance_score?: number;
  voice_consistency_score?: number;
}

interface BSAOriginStory {
  archetype_used?: string;
  emotional_arc?: string;
  versions?: BSAStoryVersion[];
}

interface BSAMissionVisionStatement {
  current?: string;
  recommended?: string;
  scores?: Record<string, number>;
}

interface BSAMissionVision {
  mission?: BSAMissionVisionStatement;
  mission_scores?: Record<string, number>;
  vision?: BSAMissionVisionStatement;
  vision_scores?: Record<string, number>;
}

interface BSAElevatorPitch {
  duration_label?: string;
  word_count?: number;
  content?: string;
  memorability_score?: number;
  clarity_score?: number;
}

interface BSAPitches {
  pitch_15s?: BSAElevatorPitch;
  pitch_30s?: BSAElevatorPitch;
  pitch_60s?: BSAElevatorPitch;
}

interface BSAChannelNarrative {
  channel?: string;
  tone?: string;
  content?: string;
  word_count?: number;
}

interface BSAChannelNarratives {
  website_about?: BSAChannelNarrative;
  social_bio?: BSAChannelNarrative;
  investor?: BSAChannelNarrative;
  press_boilerplate?: BSAChannelNarrative;
  channel_consistency_score?: number;
}

interface BSAStoryStyleGuide {
  narrative_principles?: string[];
  approved_themes?: string[];
  forbidden_themes?: string[];
  tone_guidelines?: Record<string, string>;
  story_examples?: Array<{ context?: string; example?: string }>;
}

interface BSASubBrandStory {
  sub_brand?: string;
  relationship_to_parent?: string;
  narrative_snippet?: string;
}

interface BSANarrativePackage {
  overall_confidence?: number;
  positioning_narrative_alignment?: number;
  archetype_consistency?: number;
  summary?: string;
}

function BrandStorySection({
  originStory,
  missionVision,
  pitches,
  channelNarratives,
  storyStyleGuide,
  subbrandStories,
  narrativePackage,
  confidenceScore,
  findings,
  recommendations,
}: {
  originStory?: BSAOriginStory;
  missionVision?: BSAMissionVision;
  pitches?: BSAPitches;
  channelNarratives?: BSAChannelNarratives;
  storyStyleGuide?: BSAStoryStyleGuide;
  subbrandStories?: BSASubBrandStory[];
  narrativePackage?: BSANarrativePackage;
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  const [activeTab, setActiveTab] = useState<'origin' | 'mission' | 'pitches' | 'channels' | 'guide'>('origin');

  function scoreColor(score: number) {
    if (score >= 80) return 'text-green-400';
    if (score >= 60) return 'text-amber-400';
    return 'text-red-400';
  }

  function scoreBg(score: number) {
    if (score >= 80) return 'bg-green-400';
    if (score >= 60) return 'bg-amber-400';
    return 'bg-red-400';
  }

  const tabs = [
    { key: 'origin' as const, label: 'Origin Story' },
    { key: 'mission' as const, label: 'Mission & Vision' },
    { key: 'pitches' as const, label: 'Elevator Pitches' },
    { key: 'channels' as const, label: 'Channel Narratives' },
    { key: 'guide' as const, label: 'Style Guide' },
  ];

  const versions = originStory?.versions ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-bold text-white">Brand Story & Narrative</h3>
        {confidenceScore != null && (() => {
          const pct = confidenceScore <= 1 ? Math.round(confidenceScore * 100) : Math.round(confidenceScore);
          return (
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold border ${pct >= 70 ? 'text-green-400 bg-green-400/10 border-green-400/30' : pct >= 40 ? 'text-amber-400 bg-amber-400/10 border-amber-400/30' : 'text-red-400 bg-red-400/10 border-red-400/30'}`}>
              Confidence: {pct}%
            </span>
          );
        })()}
      </div>

      {/* Narrative Package Summary */}
      {narrativePackage?.summary && (
        <div className="p-4 rounded-xl bg-brand-electric/10 border border-brand-electric/20">
          <div className="text-xs text-brand-silver/60 uppercase tracking-wider mb-1">Narrative Summary</div>
          <p className="text-sm text-white">{narrativePackage.summary}</p>
          <div className="flex gap-4 mt-3 text-xs text-brand-silver">
            {narrativePackage.overall_confidence != null && (
              <span>Overall: <span className={scoreColor(narrativePackage.overall_confidence * 100)}>{Math.round(narrativePackage.overall_confidence * 100)}%</span></span>
            )}
            {narrativePackage.positioning_narrative_alignment != null && (
              <span>Positioning Alignment: <span className={scoreColor(narrativePackage.positioning_narrative_alignment * 100)}>{Math.round(narrativePackage.positioning_narrative_alignment * 100)}%</span></span>
            )}
            {narrativePackage.archetype_consistency != null && (
              <span>Archetype Consistency: <span className={scoreColor(narrativePackage.archetype_consistency * 100)}>{Math.round(narrativePackage.archetype_consistency * 100)}%</span></span>
            )}
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 overflow-x-auto border-b border-white/10 pb-px">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors rounded-t-md ${activeTab === tab.key ? 'text-brand-electric bg-brand-electric/10 border-b-2 border-brand-electric' : 'text-brand-silver/60 hover:text-brand-silver'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab: Origin Story ──────────────────────────────── */}
      {activeTab === 'origin' && (
        <div className="space-y-4">
          {originStory?.archetype_used && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-brand-silver">Archetype:</span>
              <span className="text-brand-electric font-medium">{originStory.archetype_used}</span>
              {originStory.emotional_arc && (
                <>
                  <span className="text-brand-silver ml-4">Arc:</span>
                  <span className="text-white">{originStory.emotional_arc}</span>
                </>
              )}
            </div>
          )}
          {versions.length === 0 ? (
            <p className="text-sm text-brand-silver">No origin story versions generated.</p>
          ) : (
            versions.map((v, i) => (
              <div key={i} className="bg-brand-midnight/30 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-brand-electric uppercase tracking-wider">
                    {v.version_label ?? `Version ${i + 1}`}
                    {v.word_count != null && <span className="text-brand-silver ml-2">({v.word_count} words)</span>}
                  </span>
                  <div className="flex gap-3 text-xs text-brand-silver">
                    {v.archetype_arc_alignment != null && (
                      <span>Arc: <span className={scoreColor(v.archetype_arc_alignment * 100)}>{Math.round(v.archetype_arc_alignment * 100)}%</span></span>
                    )}
                    {v.emotional_resonance_score != null && (
                      <span>Resonance: <span className={scoreColor(v.emotional_resonance_score * 100)}>{Math.round(v.emotional_resonance_score * 100)}%</span></span>
                    )}
                    {v.voice_consistency_score != null && (
                      <span>Voice: <span className={scoreColor(v.voice_consistency_score * 100)}>{Math.round(v.voice_consistency_score * 100)}%</span></span>
                    )}
                  </div>
                </div>
                {v.content && (
                  <div className="bg-white/5 rounded-lg p-3 border border-white/10 max-h-60 overflow-y-auto">
                    <MarkdownMessage content={v.content} />
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Tab: Mission & Vision ─────────────────────────── */}
      {activeTab === 'mission' && (
        <div className="space-y-4">
          {/* Mission */}
          <div className="space-y-3">
            <h4 className="text-sm font-semibold text-white">Mission Statement</h4>
            {missionVision?.mission?.current && (
              <div className="bg-brand-midnight/30 rounded-lg p-3">
                <p className="text-xs text-brand-silver/60 uppercase tracking-wider mb-1">Current</p>
                <p className="text-sm text-brand-silver italic">{missionVision.mission.current}</p>
              </div>
            )}
            {missionVision?.mission?.recommended && (
              <div className="bg-brand-electric/10 rounded-lg p-3 border border-brand-electric/20">
                <p className="text-xs text-brand-silver/60 uppercase tracking-wider mb-1">Recommended</p>
                <p className="text-sm text-white">{missionVision.mission.recommended}</p>
              </div>
            )}
            {(missionVision?.mission_scores || missionVision?.mission?.scores) && (() => {
              const scores = missionVision?.mission_scores ?? missionVision?.mission?.scores ?? {};
              return (
                <div className="flex gap-4 text-xs text-brand-silver">
                  {Object.entries(scores).map(([k, v]) => (
                    <span key={k}>{k.replace(/_/g, ' ')}: <span className={scoreColor(Number(v) * 100)}>{Math.round(Number(v) * 100)}%</span></span>
                  ))}
                </div>
              );
            })()}
          </div>
          {/* Vision */}
          <div className="space-y-3">
            <h4 className="text-sm font-semibold text-white">Vision Statement</h4>
            {missionVision?.vision?.current && (
              <div className="bg-brand-midnight/30 rounded-lg p-3">
                <p className="text-xs text-brand-silver/60 uppercase tracking-wider mb-1">Current</p>
                <p className="text-sm text-brand-silver italic">{missionVision.vision.current}</p>
              </div>
            )}
            {missionVision?.vision?.recommended && (
              <div className="bg-brand-electric/10 rounded-lg p-3 border border-brand-electric/20">
                <p className="text-xs text-brand-silver/60 uppercase tracking-wider mb-1">Recommended</p>
                <p className="text-sm text-white">{missionVision.vision.recommended}</p>
              </div>
            )}
            {(missionVision?.vision_scores || missionVision?.vision?.scores) && (() => {
              const scores = missionVision?.vision_scores ?? missionVision?.vision?.scores ?? {};
              return (
                <div className="flex gap-4 text-xs text-brand-silver">
                  {Object.entries(scores).map(([k, v]) => (
                    <span key={k}>{k.replace(/_/g, ' ')}: <span className={scoreColor(Number(v) * 100)}>{Math.round(Number(v) * 100)}%</span></span>
                  ))}
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* ── Tab: Elevator Pitches ─────────────────────────── */}
      {activeTab === 'pitches' && (
        <div className="space-y-4">
          {[
            { key: 'pitch_15s', label: '15-Second Pitch', data: pitches?.pitch_15s },
            { key: 'pitch_30s', label: '30-Second Pitch', data: pitches?.pitch_30s },
            { key: 'pitch_60s', label: '60-Second Pitch', data: pitches?.pitch_60s },
          ].map(({ key, label, data }) =>
            data ? (
              <div key={key} className="bg-brand-midnight/30 rounded-lg p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-brand-electric uppercase tracking-wider">{label}</span>
                  <div className="flex gap-3 text-xs text-brand-silver">
                    {data.word_count != null && <span>{data.word_count} words</span>}
                    {data.memorability_score != null && (
                      <span>Memorability: <span className={scoreColor(data.memorability_score * 100)}>{Math.round(data.memorability_score * 100)}%</span></span>
                    )}
                    {data.clarity_score != null && (
                      <span>Clarity: <span className={scoreColor(data.clarity_score * 100)}>{Math.round(data.clarity_score * 100)}%</span></span>
                    )}
                  </div>
                </div>
                {data.content && (
                  <div className="bg-white/5 rounded-lg p-3 border border-white/10">
                    <p className="text-sm text-white">{data.content}</p>
                  </div>
                )}
              </div>
            ) : null,
          )}
          {!pitches?.pitch_15s && !pitches?.pitch_30s && !pitches?.pitch_60s && (
            <p className="text-sm text-brand-silver">No elevator pitches generated.</p>
          )}
        </div>
      )}

      {/* ── Tab: Channel Narratives ───────────────────────── */}
      {activeTab === 'channels' && (
        <div className="space-y-4">
          {channelNarratives?.channel_consistency_score != null && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-brand-silver">Channel Consistency:</span>
              <div className="flex-1 max-w-48 h-2 rounded-full bg-white/10 overflow-hidden">
                <div
                  className={`h-full rounded-full ${scoreBg(channelNarratives.channel_consistency_score * 100)}`}
                  style={{ width: `${Math.round(channelNarratives.channel_consistency_score * 100)}%` }}
                />
              </div>
              <span className={`text-sm font-bold ${scoreColor(channelNarratives.channel_consistency_score * 100)}`}>
                {Math.round(channelNarratives.channel_consistency_score * 100)}%
              </span>
            </div>
          )}
          {[
            { key: 'website_about', label: 'Website About', data: channelNarratives?.website_about },
            { key: 'social_bio', label: 'Social Media Bio', data: channelNarratives?.social_bio },
            { key: 'investor', label: 'Investor Narrative', data: channelNarratives?.investor },
            { key: 'press_boilerplate', label: 'Press Boilerplate', data: channelNarratives?.press_boilerplate },
          ].map(({ key, label, data }) =>
            data ? (
              <div key={key} className="bg-brand-midnight/30 rounded-lg p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-brand-electric uppercase tracking-wider">{label}</span>
                  <div className="flex gap-3 text-xs text-brand-silver">
                    {data.tone && <span>Tone: {data.tone}</span>}
                    {data.word_count != null && <span>{data.word_count} words</span>}
                  </div>
                </div>
                {data.content && (
                  <div className="bg-white/5 rounded-lg p-3 border border-white/10">
                    <MarkdownMessage content={data.content} />
                  </div>
                )}
              </div>
            ) : null,
          )}

          {/* Sub-brand stories */}
          {subbrandStories && subbrandStories.length > 0 && (
            <div className="space-y-3 mt-4">
              <h4 className="text-sm font-semibold text-white">Sub-Brand Story Variations</h4>
              {subbrandStories.map((sb, i) => (
                <div key={i} className="bg-brand-midnight/30 rounded-lg p-3 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-brand-electric">{sb.sub_brand ?? `Sub-brand ${i + 1}`}</span>
                    {sb.relationship_to_parent && (
                      <span className="text-[10px] text-brand-silver bg-white/5 px-1.5 py-0.5 rounded">{sb.relationship_to_parent}</span>
                    )}
                  </div>
                  {sb.narrative_snippet && <p className="text-sm text-white">{sb.narrative_snippet}</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Style Guide ──────────────────────────────── */}
      {activeTab === 'guide' && (
        <div className="space-y-4">
          {!storyStyleGuide ? (
            <p className="text-sm text-brand-silver">No story style guide available.</p>
          ) : (
            <>
              {storyStyleGuide.narrative_principles && storyStyleGuide.narrative_principles.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-brand-silver mb-2">Narrative Principles</p>
                  <ul className="space-y-1">
                    {storyStyleGuide.narrative_principles.map((p, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-white">
                        <span className="text-brand-electric mt-0.5">&#9672;</span>
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {storyStyleGuide.approved_themes && storyStyleGuide.approved_themes.length > 0 && (
                  <div className="bg-green-400/5 rounded-lg p-3 border border-green-400/20">
                    <p className="text-xs font-medium text-green-400 mb-2">Approved Themes</p>
                    <div className="flex flex-wrap gap-1.5">
                      {storyStyleGuide.approved_themes.map((t, i) => (
                        <span key={i} className="text-xs bg-green-400/10 text-green-400 px-2 py-0.5 rounded">{t}</span>
                      ))}
                    </div>
                  </div>
                )}
                {storyStyleGuide.forbidden_themes && storyStyleGuide.forbidden_themes.length > 0 && (
                  <div className="bg-red-400/5 rounded-lg p-3 border border-red-400/20">
                    <p className="text-xs font-medium text-red-400 mb-2">Forbidden Themes</p>
                    <div className="flex flex-wrap gap-1.5">
                      {storyStyleGuide.forbidden_themes.map((t, i) => (
                        <span key={i} className="text-xs bg-red-400/10 text-red-400 px-2 py-0.5 rounded">{t}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              {storyStyleGuide.tone_guidelines && Object.keys(storyStyleGuide.tone_guidelines).length > 0 && (
                <div>
                  <p className="text-xs font-medium text-brand-silver mb-2">Tone Guidelines</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {Object.entries(storyStyleGuide.tone_guidelines).map(([k, v]) => (
                      <div key={k} className="bg-brand-midnight/30 rounded-lg p-3">
                        <p className="text-xs text-brand-electric capitalize">{k.replace(/_/g, ' ')}</p>
                        <p className="text-sm text-white mt-1">{v}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {storyStyleGuide.story_examples && storyStyleGuide.story_examples.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-brand-silver mb-2">Story Examples</p>
                  {storyStyleGuide.story_examples.map((ex, i) => (
                    <div key={i} className="bg-brand-midnight/30 rounded-lg p-3 mb-2">
                      {ex.context && <p className="text-xs text-brand-electric mb-1">{ex.context}</p>}
                      {ex.example && <p className="text-sm text-white italic">&ldquo;{ex.example}&rdquo;</p>}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Findings & Recommendations */}
          {findings && findings.length > 0 && (
            <div>
              <p className="text-xs font-medium text-brand-silver mb-1">Findings</p>
              <ul className="space-y-1">
                {findings.map((f, i) => (
                  <li key={i} className="text-sm text-brand-silver">&#8226; {f}</li>
                ))}
              </ul>
            </div>
          )}
          {recommendations && recommendations.length > 0 && (
            <div>
              <p className="text-xs font-medium text-brand-silver mb-1">Recommendations</p>
              <ul className="space-y-1">
                {recommendations.map((r, i) => (
                  <li key={i} className="text-sm text-brand-silver">&#8226; {r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BrandNamingSection({
  nameCandidates,
  shortlistedNames,
  taglines,
  namingBrief,
  confidenceScore,
  findings,
  recommendations,
}: {
  nameCandidates?: NTANameCandidate[];
  shortlistedNames?: string[];
  taglines?: NTATagline[];
  namingBrief?: NTANamingBrief;
  availabilityResults?: Record<string, unknown>;
  scoringSummary?: Record<string, unknown>;
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  const [activeTab, setActiveTab] = useState<'candidates' | 'availability' | 'taglines' | 'brief'>('candidates');

  const tabs = [
    { id: 'candidates' as const, label: 'Name Candidates' },
    { id: 'availability' as const, label: 'Availability' },
    { id: 'taglines' as const, label: 'Taglines' },
    { id: 'brief' as const, label: 'Naming Brief' },
  ];

  const shortlistSet = new Set(shortlistedNames ?? []);
  const sortedCandidates = [...(nameCandidates ?? [])].sort(
    (a, b) => (b.scores?.overall ?? 0) - (a.scores?.overall ?? 0),
  );

  return (
    <div className="glass-card p-6 rounded-xl space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-brand-electric flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-brand-electric" />
          Brand Naming & Tagline
        </h3>
        {confidenceScore != null && (
          <span className="text-xs text-brand-silver">
            Confidence: {(confidenceScore * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-brand-midnight/40 rounded-lg p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === t.id
                ? 'bg-brand-electric/20 text-brand-electric'
                : 'text-brand-silver hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Tab: Name Candidates ─────────────────────────── */}
      {activeTab === 'candidates' && (
        <div className="space-y-3">
          {sortedCandidates.length === 0 ? (
            <p className="text-sm text-brand-silver">No name candidates generated.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-brand-silver border-b border-white/10">
                    <th className="text-left py-2 px-2">#</th>
                    <th className="text-left py-2 px-2">Name</th>
                    <th className="text-left py-2 px-2">Type</th>
                    <th className="text-right py-2 px-2">Overall</th>
                    <th className="text-right py-2 px-2">Linguistic</th>
                    <th className="text-right py-2 px-2">Memorability</th>
                    <th className="text-right py-2 px-2">Strategy</th>
                    <th className="text-right py-2 px-2">Availability</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedCandidates.map((c, i) => (
                    <tr
                      key={c.name}
                      className={`border-b border-white/5 ${
                        shortlistSet.has(c.name) ? 'bg-brand-electric/5' : ''
                      }`}
                    >
                      <td className="py-2 px-2 text-brand-silver">{i + 1}</td>
                      <td className="py-2 px-2 font-medium text-white">
                        {c.name}
                        {shortlistSet.has(c.name) && (
                          <span className="ml-2 text-[10px] bg-brand-electric/20 text-brand-electric px-1.5 py-0.5 rounded">
                            Shortlisted
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-2 text-brand-silver capitalize">{c.naming_type ?? '—'}</td>
                      <td className="py-2 px-2 text-right font-mono text-brand-electric">{c.scores?.overall?.toFixed(1) ?? '—'}</td>
                      <td className="py-2 px-2 text-right font-mono text-brand-silver">{c.scores?.linguistic?.toFixed(1) ?? '—'}</td>
                      <td className="py-2 px-2 text-right font-mono text-brand-silver">{c.scores?.memorability?.toFixed(1) ?? '—'}</td>
                      <td className="py-2 px-2 text-right font-mono text-brand-silver">{c.scores?.strategy_alignment?.toFixed(1) ?? '—'}</td>
                      <td className="py-2 px-2 text-right font-mono text-brand-silver">{c.scores?.availability?.toFixed(1) ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {/* Rationale for top 3 */}
          {sortedCandidates.slice(0, 3).map((c) => c.rationale ? (
            <div key={c.name} className="bg-brand-midnight/30 rounded-lg p-3">
              <span className="text-xs font-medium text-brand-electric">{c.name}</span>
              <p className="text-xs text-brand-silver mt-1">{c.rationale}</p>
            </div>
          ) : null)}
        </div>
      )}

      {/* ── Tab: Availability ────────────────────────────── */}
      {activeTab === 'availability' && (
        <div className="space-y-3">
          {sortedCandidates.length === 0 ? (
            <p className="text-sm text-brand-silver">No availability data.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-brand-silver border-b border-white/10">
                    <th className="text-left py-2 px-2">Name</th>
                    <th className="text-center py-2 px-2">.com</th>
                    <th className="text-center py-2 px-2">.io</th>
                    <th className="text-center py-2 px-2">.co</th>
                    <th className="text-center py-2 px-2">Twitter</th>
                    <th className="text-center py-2 px-2">Instagram</th>
                    <th className="text-center py-2 px-2">LinkedIn</th>
                    <th className="text-center py-2 px-2">Trademark</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedCandidates.map((c) => {
                    const a = c.availability;
                    const badge = (val: boolean | null | undefined) => {
                      if (val === true) return <span className="text-green-400">✓</span>;
                      if (val === false) return <span className="text-red-400">✗</span>;
                      return <span className="text-brand-silver">—</span>;
                    };
                    return (
                      <tr key={c.name} className="border-b border-white/5">
                        <td className="py-2 px-2 font-medium text-white">{c.name}</td>
                        <td className="py-2 px-2 text-center">{badge(a?.domain_com)}</td>
                        <td className="py-2 px-2 text-center">{badge(a?.domain_io)}</td>
                        <td className="py-2 px-2 text-center">{badge(a?.domain_co)}</td>
                        <td className="py-2 px-2 text-center">{badge(a?.twitter)}</td>
                        <td className="py-2 px-2 text-center">{badge(a?.instagram)}</td>
                        <td className="py-2 px-2 text-center">{badge(a?.linkedin)}</td>
                        <td className="py-2 px-2 text-center">{badge(a?.trademark_clear)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Taglines ────────────────────────────────── */}
      {activeTab === 'taglines' && (
        <div className="space-y-3">
          {(!taglines || taglines.length === 0) ? (
            <p className="text-sm text-brand-silver">No taglines generated.</p>
          ) : (
            taglines.map((t, i) => (
              <div key={i} className="bg-brand-midnight/30 rounded-lg p-4 space-y-2">
                <p className="text-white font-medium">&ldquo;{t.tagline}&rdquo;</p>
                {t.name && (
                  <p className="text-xs text-brand-electric">For: {t.name}</p>
                )}
                {t.emotional_appeal && (
                  <p className="text-xs text-brand-silver">{t.emotional_appeal}</p>
                )}
                <div className="flex gap-4 text-xs text-brand-silver">
                  {t.memorability_score != null && (
                    <span>Memorability: {t.memorability_score.toFixed(0)}/100</span>
                  )}
                  {t.positioning_alignment && (
                    <span>Positioning: {t.positioning_alignment}</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Tab: Naming Brief ────────────────────────────── */}
      {activeTab === 'brief' && (
        <div className="space-y-4">
          {!namingBrief ? (
            <p className="text-sm text-brand-silver">No naming brief available.</p>
          ) : (
            <>
              {namingBrief.recommended_name && (
                <div className="bg-brand-electric/10 rounded-lg p-4 border border-brand-electric/20">
                  <p className="text-xs text-brand-silver uppercase tracking-wider mb-1">Recommended Name</p>
                  <p className="text-xl font-bold text-brand-electric">{namingBrief.recommended_name}</p>
                  {namingBrief.recommended_tagline && (
                    <p className="text-sm text-white mt-1 italic">&ldquo;{namingBrief.recommended_tagline}&rdquo;</p>
                  )}
                </div>
              )}
              {namingBrief.rationale && (
                <div>
                  <p className="text-xs font-medium text-brand-silver mb-1">Rationale</p>
                  <p className="text-sm text-white">{namingBrief.rationale}</p>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {namingBrief.positioning_alignment && (
                  <div className="bg-brand-midnight/30 rounded-lg p-3">
                    <p className="text-xs text-brand-silver">Positioning Alignment</p>
                    <p className="text-sm text-white mt-1">{namingBrief.positioning_alignment}</p>
                  </div>
                )}
                {namingBrief.personality_alignment && (
                  <div className="bg-brand-midnight/30 rounded-lg p-3">
                    <p className="text-xs text-brand-silver">Personality Alignment</p>
                    <p className="text-sm text-white mt-1">{namingBrief.personality_alignment}</p>
                  </div>
                )}
                {namingBrief.architecture_fit && (
                  <div className="bg-brand-midnight/30 rounded-lg p-3">
                    <p className="text-xs text-brand-silver">Architecture Fit</p>
                    <p className="text-sm text-white mt-1">{namingBrief.architecture_fit}</p>
                  </div>
                )}
              </div>
              {namingBrief.next_steps && namingBrief.next_steps.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-brand-silver mb-2">Next Steps</p>
                  <ul className="space-y-1">
                    {namingBrief.next_steps.map((step, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-white">
                        <span className="text-brand-electric mt-0.5">→</span>
                        {step}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          {/* Findings & Recommendations */}
          {findings && findings.length > 0 && (
            <div>
              <p className="text-xs font-medium text-brand-silver mb-1">Findings</p>
              <ul className="space-y-1">
                {findings.map((f, i) => (
                  <li key={i} className="text-sm text-brand-silver">• {f}</li>
                ))}
              </ul>
            </div>
          )}
          {recommendations && recommendations.length > 0 && (
            <div>
              <p className="text-xs font-medium text-brand-silver mb-1">Recommendations</p>
              <ul className="space-y-1">
                {recommendations.map((r, i) => (
                  <li key={i} className="text-sm text-brand-silver">• {r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
 * Brand Personality & Values (BPV) Section — 6 tabs
 * ══════════════════════════════════════════════════════════════════════════ */

interface BPVAakerDimension {
  dimension: string;
  score: number;
  sub_traits?: Array<{ name: string; score: number }>;
}

interface BPVAakerProfile {
  dimensions: BPVAakerDimension[];
  primary_dimension?: string;
  secondary_dimension?: string;
  differentiation_score?: number;
}

interface BPVArchetypeDetail {
  name?: string;
  core_desire?: string;
  fear?: string;
  strategy?: string;
  gift?: string;
  shadow?: string;
  brand_expression?: string;
}

interface BPVArchetype {
  primary: string | BPVArchetypeDetail;
  secondary?: string | BPVArchetypeDetail;
  primary_detail?: BPVArchetypeDetail;
  secondary_detail?: BPVArchetypeDetail;
  blend_rationale?: string;
  resonance_score?: number;
}

interface BPVValueItem {
  name: string;
  definition?: string;
  behavioral_manifestation?: string;
}

interface BPVValuesHierarchy {
  core: BPVValueItem[];
  supporting?: BPVValueItem[];
  aspirational?: BPVValueItem[];
  authenticity_score?: number;
}

interface BPVEmotionalMap {
  personas: Array<{
    persona: string;
    emotions: Array<{ emotion: string; intensity: number }>;
  }>;
  consistency_score?: number;
}

interface BPVVoiceMatrix {
  tone_spectrum?: Array<{
    dimension?: string; attribute?: string;
    low_end?: string; min_label?: string;
    high_end?: string; max_label?: string;
    position: number;
  }>;
  vocabulary?: { preferred: string[]; avoided: string[] };
  style?: Record<string, string>;
  humor?: string | { overall_tone?: string; do_examples?: string[]; dont_examples?: string[]; [key: string]: unknown };
  dos?: string[];
  donts?: string[];
  channel_adaptations?: Array<{ channel: string; adaptation?: string; guideline?: string }>;
}

interface BPVCharacterBrief {
  persona_card?: {
    name?: string;
    personality_snapshot?: string;
    core_belief?: string;
    superpower?: string;
    fear?: string;
    communication_style?: string;
    emotional_signature?: string[];
  };
  executive_summary?: string;
  positioning_alignment_score?: number;
}

function BrandPersonalitySection({
  aakerProfile,
  archetype,
  valuesHierarchy,
  emotionalMap,
  voiceMatrix,
  characterBrief,
  confidenceScore,
  findings,
  recommendations,
}: {
  aakerProfile?: BPVAakerProfile;
  archetype?: BPVArchetype;
  valuesHierarchy?: BPVValuesHierarchy;
  emotionalMap?: BPVEmotionalMap;
  voiceMatrix?: BPVVoiceMatrix;
  characterBrief?: BPVCharacterBrief;
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  const [activeTab, setActiveTab] = useState<'profile' | 'archetype' | 'values' | 'emotional' | 'voice' | 'brief'>('profile');

  function scoreColor(score: number) {
    if (score >= 80) return 'text-green-400';
    if (score >= 60) return 'text-amber-400';
    return 'text-red-400';
  }

  function scoreBg(score: number) {
    if (score >= 80) return 'bg-green-400';
    if (score >= 60) return 'bg-amber-400';
    return 'bg-red-400';
  }

  const tabs = [
    { key: 'profile' as const, label: 'Personality Profile' },
    { key: 'archetype' as const, label: 'Archetype' },
    { key: 'values' as const, label: 'Values' },
    { key: 'emotional' as const, label: 'Emotional Map' },
    { key: 'voice' as const, label: 'Voice Matrix' },
    { key: 'brief' as const, label: 'Character Brief' },
  ];

  // Helper: archetype.primary/secondary may be a string OR an object with {name, fear, gift, ...}
  function archetypeName(val: string | BPVArchetypeDetail | undefined): string | undefined {
    if (!val) return undefined;
    if (typeof val === 'string') return val;
    return val.name ?? 'Unknown';
  }
  function archetypeDetail(val: string | BPVArchetypeDetail | undefined, detail: BPVArchetypeDetail | undefined): BPVArchetypeDetail | undefined {
    if (detail) return detail;
    if (val && typeof val === 'object') return val;
    return undefined;
  }

  const primaryName = archetypeName(archetype?.primary);
  const secondaryName = archetypeName(archetype?.secondary);
  const primaryDetail = archetypeDetail(archetype?.primary, archetype?.primary_detail);
  const secondaryDetail = archetypeDetail(archetype?.secondary, archetype?.secondary_detail);

  const dimensions = aakerProfile?.dimensions ?? [];
  const maxDim = dimensions.length > 0 ? Math.max(...dimensions.map(d => d.score)) : 100;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-bold text-white">Brand Personality & Values</h3>
        {confidenceScore != null && (() => {
          const pct = confidenceScore <= 1 ? Math.round(confidenceScore * 100) : Math.round(confidenceScore);
          return (
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold border ${pct >= 70 ? 'text-green-400 bg-green-400/10 border-green-400/30' : pct >= 40 ? 'text-amber-400 bg-amber-400/10 border-amber-400/30' : 'text-red-400 bg-red-400/10 border-red-400/30'}`}>
              Confidence: {pct}%
            </span>
          );
        })()}
      </div>

      {/* Archetype Badge */}
      {primaryName && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-brand-electric/10 border border-brand-electric/20">
          <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-brand-electric/20 flex items-center justify-center text-brand-electric text-lg">&#9672;</div>
          <div>
            <div className="text-xs text-brand-silver/60 uppercase tracking-wider">Primary Archetype</div>
            <div className="text-lg font-bold text-white">{primaryName}{secondaryName ? ` / ${secondaryName}` : ''}</div>
          </div>
          {archetype?.resonance_score != null && (
            <span className={`ml-auto text-sm font-bold ${scoreColor(archetype.resonance_score)}`}>
              Resonance: {Math.round(archetype.resonance_score)}%
            </span>
          )}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 overflow-x-auto border-b border-white/10 pb-px">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors rounded-t-md ${activeTab === tab.key ? 'text-brand-electric bg-brand-electric/10 border-b-2 border-brand-electric' : 'text-brand-silver/60 hover:text-brand-silver'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab: Personality Profile (Aaker 5D Radar) ─────────────── */}
      {activeTab === 'profile' && (
        <div className="space-y-4">
          {dimensions.length > 0 ? (
            <>
              {/* Horizontal bar chart for Aaker dimensions */}
              <div className="space-y-3">
                {dimensions.map((dim) => {
                  const label = (dim.dimension || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                  const isPrimary = dim.dimension === aakerProfile?.primary_dimension;
                  const isSecondary = dim.dimension === aakerProfile?.secondary_dimension;
                  return (
                    <div key={dim.dimension} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-white font-medium">{label}</span>
                          {isPrimary && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand-electric/20 text-brand-electric font-bold">PRIMARY</span>}
                          {isSecondary && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-400/20 text-purple-400 font-bold">SECONDARY</span>}
                        </div>
                        <span className={`text-sm font-bold ${scoreColor(dim.score)}`}>{Math.round(dim.score)}</span>
                      </div>
                      <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all ${scoreBg(dim.score)}`} style={{ width: `${Math.min(100, (dim.score / maxDim) * 100)}%`, opacity: 0.8 }} />
                      </div>
                      {/* Sub-traits */}
                      {dim.sub_traits && dim.sub_traits.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {dim.sub_traits.map((st) => (
                            <span key={st.name} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-brand-silver/70">
                              {st.name}: {Math.round(st.score)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Differentiation Score */}
              {aakerProfile?.differentiation_score != null && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-white/5 border border-white/10">
                  <span className="text-xs text-brand-silver/60">Differentiation Score:</span>
                  <span className={`text-sm font-bold ${scoreColor(aakerProfile.differentiation_score)}`}>
                    {Math.round(aakerProfile.differentiation_score)}
                  </span>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-brand-silver/50 italic">No Aaker dimension data available.</p>
          )}
        </div>
      )}

      {/* ── Tab: Archetype ────────────────────────────────────────── */}
      {activeTab === 'archetype' && (
        <div className="space-y-4">
          {primaryName ? (
            <>
              {/* Primary Archetype Card */}
              <div className="p-4 rounded-xl bg-white/5 border border-white/10 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-base font-bold text-white">Primary: {primaryName}</h4>
                  {archetype?.resonance_score != null && (
                    <span className={`text-sm font-bold ${scoreColor(archetype.resonance_score)}`}>
                      {Math.round(archetype.resonance_score)}% resonance
                    </span>
                  )}
                </div>
                {primaryDetail && (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {primaryDetail.core_desire && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Core Desire:</span> <span className="text-white">{primaryDetail.core_desire}</span></div>
                    )}
                    {primaryDetail.fear && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Fear:</span> <span className="text-white">{primaryDetail.fear}</span></div>
                    )}
                    {primaryDetail.strategy && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Strategy:</span> <span className="text-white">{primaryDetail.strategy}</span></div>
                    )}
                    {primaryDetail.gift && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Gift:</span> <span className="text-white">{primaryDetail.gift}</span></div>
                    )}
                    {primaryDetail.shadow && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Shadow:</span> <span className="text-white">{primaryDetail.shadow}</span></div>
                    )}
                    {primaryDetail.brand_expression && (
                      <div className="col-span-2 p-2 rounded bg-white/5"><span className="text-brand-silver/50">Brand Expression:</span> <span className="text-white">{primaryDetail.brand_expression}</span></div>
                    )}
                  </div>
                )}
              </div>

              {/* Secondary Archetype Card */}
              {secondaryName && (
                <div className="p-4 rounded-xl bg-white/5 border border-white/10 space-y-3">
                  <h4 className="text-sm font-bold text-purple-400">Secondary: {secondaryName}</h4>
                  {secondaryDetail && (
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {secondaryDetail.core_desire && (
                        <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Core Desire:</span> <span className="text-white">{secondaryDetail.core_desire}</span></div>
                      )}
                      {secondaryDetail.gift && (
                        <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Gift:</span> <span className="text-white">{secondaryDetail.gift}</span></div>
                      )}
                      {secondaryDetail.brand_expression && (
                        <div className="col-span-2 p-2 rounded bg-white/5"><span className="text-brand-silver/50">Brand Expression:</span> <span className="text-white">{secondaryDetail.brand_expression}</span></div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Blend Rationale */}
              {archetype?.blend_rationale && (
                <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                  <span className="text-xs text-brand-silver/50 block mb-1">Blend Rationale</span>
                  <p className="text-sm text-brand-silver">{archetype.blend_rationale}</p>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-brand-silver/50 italic">No archetype data available.</p>
          )}
        </div>
      )}

      {/* ── Tab: Values Hierarchy ─────────────────────────────────── */}
      {activeTab === 'values' && (
        <div className="space-y-4">
          {valuesHierarchy ? (
            <>
              {/* Core Values */}
              {valuesHierarchy.core.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Core Values</h4>
                  {valuesHierarchy.core.map((v, i) => (
                    <div key={i} className="p-3 rounded-lg bg-amber-400/5 border border-amber-400/20">
                      <div className="text-sm font-bold text-white">{v.name}</div>
                      {v.definition && <p className="text-xs text-brand-silver/70 mt-1">{v.definition}</p>}
                      {v.behavioral_manifestation && <p className="text-xs text-brand-silver/50 mt-1 italic">{v.behavioral_manifestation}</p>}
                    </div>
                  ))}
                </div>
              )}

              {/* Supporting Values */}
              {valuesHierarchy.supporting && valuesHierarchy.supporting.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">Supporting Values</h4>
                  {valuesHierarchy.supporting.map((v, i) => (
                    <div key={i} className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <div className="text-sm font-bold text-white">{v.name}</div>
                      {v.definition && <p className="text-xs text-brand-silver/70 mt-1">{v.definition}</p>}
                      {v.behavioral_manifestation && <p className="text-xs text-brand-silver/50 mt-1 italic">{v.behavioral_manifestation}</p>}
                    </div>
                  ))}
                </div>
              )}

              {/* Aspirational Values */}
              {valuesHierarchy.aspirational && valuesHierarchy.aspirational.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-blue-400 uppercase tracking-wider">Aspirational Values</h4>
                  {valuesHierarchy.aspirational.map((v, i) => (
                    <div key={i} className="p-3 rounded-lg bg-blue-400/5 border border-blue-400/20">
                      <div className="text-sm font-bold text-white">{v.name}</div>
                      {v.definition && <p className="text-xs text-brand-silver/70 mt-1">{v.definition}</p>}
                      {v.behavioral_manifestation && <p className="text-xs text-brand-silver/50 mt-1 italic">{v.behavioral_manifestation}</p>}
                    </div>
                  ))}
                </div>
              )}

              {/* Authenticity Score */}
              {valuesHierarchy.authenticity_score != null && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-white/5 border border-white/10">
                  <span className="text-xs text-brand-silver/60">Authenticity Score:</span>
                  <span className={`text-sm font-bold ${scoreColor(valuesHierarchy.authenticity_score)}`}>
                    {Math.round(valuesHierarchy.authenticity_score)}%
                  </span>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-brand-silver/50 italic">No values data available.</p>
          )}
        </div>
      )}

      {/* ── Tab: Emotional Map ────────────────────────────────────── */}
      {activeTab === 'emotional' && (
        <div className="space-y-4">
          {emotionalMap?.personas && emotionalMap.personas.length > 0 ? (
            <>
              {/* Emotion intensity table */}
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left py-2 px-2 text-brand-silver/50 font-medium">Persona</th>
                      {emotionalMap.personas[0]?.emotions.map((e) => (
                        <th key={e.emotion} className="text-center py-2 px-2 text-brand-silver/50 font-medium capitalize">{e.emotion}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {emotionalMap.personas.map((p, pi) => (
                      <tr key={pi} className="border-b border-white/5">
                        <td className="py-2 px-2 text-white font-medium">{p.persona}</td>
                        {p.emotions.map((e) => {
                          const intensity = Math.round(e.intensity);
                          const bg = intensity >= 70 ? 'bg-brand-electric/30' : intensity >= 40 ? 'bg-amber-400/20' : 'bg-white/5';
                          return (
                            <td key={e.emotion} className={`text-center py-2 px-2 ${bg}`}>
                              <span className={scoreColor(intensity)}>{intensity}</span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Consistency Score */}
              {emotionalMap.consistency_score != null && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-white/5 border border-white/10">
                  <span className="text-xs text-brand-silver/60">Emotional Consistency:</span>
                  <span className={`text-sm font-bold ${scoreColor(emotionalMap.consistency_score)}`}>
                    {Math.round(emotionalMap.consistency_score)}%
                  </span>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-brand-silver/50 italic">No emotional map data available.</p>
          )}
        </div>
      )}

      {/* ── Tab: Voice Matrix ─────────────────────────────────────── */}
      {activeTab === 'voice' && (
        <div className="space-y-4">
          {voiceMatrix ? (
            <>
              {/* Tone Spectrum */}
              {voiceMatrix.tone_spectrum && voiceMatrix.tone_spectrum.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">Tone Spectrum</h4>
                  {voiceMatrix.tone_spectrum.map((t, idx) => (
                    <div key={t.dimension || t.attribute || idx} className="space-y-1">
                      <div className="flex justify-between text-xs text-brand-silver/50">
                        <span>{t.low_end || t.min_label}</span>
                        <span className="text-white font-medium">{t.dimension || t.attribute}</span>
                        <span>{t.high_end || t.max_label}</span>
                      </div>
                      <div className="relative w-full h-2 bg-white/10 rounded-full">
                        <div className="absolute top-0 h-2 w-3 rounded-full bg-brand-electric" style={{ left: `${Math.min(100, Math.max(0, t.position))}%`, transform: 'translateX(-50%)' }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Vocabulary */}
              {voiceMatrix.vocabulary && (
                <div className="grid grid-cols-2 gap-3">
                  {voiceMatrix.vocabulary.preferred && voiceMatrix.vocabulary.preferred.length > 0 && (
                    <div className="p-3 rounded-lg bg-green-400/5 border border-green-400/20">
                      <h5 className="text-[10px] font-bold text-green-400 uppercase mb-2">Preferred Words</h5>
                      <div className="flex flex-wrap gap-1">
                        {voiceMatrix.vocabulary.preferred.map((w) => (
                          <span key={w} className="text-[10px] px-1.5 py-0.5 rounded bg-green-400/10 text-green-300">{w}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {voiceMatrix.vocabulary.avoided && voiceMatrix.vocabulary.avoided.length > 0 && (
                    <div className="p-3 rounded-lg bg-red-400/5 border border-red-400/20">
                      <h5 className="text-[10px] font-bold text-red-400 uppercase mb-2">Avoided Words</h5>
                      <div className="flex flex-wrap gap-1">
                        {voiceMatrix.vocabulary.avoided.map((w) => (
                          <span key={w} className="text-[10px] px-1.5 py-0.5 rounded bg-red-400/10 text-red-300">{w}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Dos / Don'ts */}
              {(voiceMatrix.dos || voiceMatrix.donts) && (
                <div className="grid grid-cols-2 gap-3">
                  {voiceMatrix.dos && voiceMatrix.dos.length > 0 && (
                    <div className="p-3 rounded-lg bg-green-400/5 border border-green-400/20">
                      <h5 className="text-[10px] font-bold text-green-400 uppercase mb-2">Do</h5>
                      <ul className="space-y-1">
                        {voiceMatrix.dos.map((d, i) => (
                          <li key={i} className="text-xs text-brand-silver flex gap-1.5"><span className="text-green-400">+</span>{d}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {voiceMatrix.donts && voiceMatrix.donts.length > 0 && (
                    <div className="p-3 rounded-lg bg-red-400/5 border border-red-400/20">
                      <h5 className="text-[10px] font-bold text-red-400 uppercase mb-2">Don&apos;t</h5>
                      <ul className="space-y-1">
                        {voiceMatrix.donts.map((d, i) => (
                          <li key={i} className="text-xs text-brand-silver flex gap-1.5"><span className="text-red-400">-</span>{d}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Channel Adaptations */}
              {voiceMatrix.channel_adaptations && voiceMatrix.channel_adaptations.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">Channel Adaptations</h4>
                  {voiceMatrix.channel_adaptations.map((ch) => (
                    <div key={ch.channel} className="flex gap-3 p-2 rounded bg-white/5 border border-white/10">
                      <span className="text-xs font-bold text-brand-electric min-w-[80px]">{ch.channel}</span>
                      <span className="text-xs text-brand-silver">{ch.adaptation || ch.guideline}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-brand-silver/50 italic">No voice matrix data available.</p>
          )}
        </div>
      )}

      {/* ── Tab: Character Brief ──────────────────────────────────── */}
      {activeTab === 'brief' && (
        <div className="space-y-4">
          {characterBrief ? (
            <>
              {/* Persona Card */}
              {characterBrief.persona_card && (
                <div className="p-4 rounded-xl bg-gradient-to-br from-brand-electric/10 to-purple-500/10 border border-brand-electric/20 space-y-3">
                  {characterBrief.persona_card.name && (
                    <h4 className="text-base font-bold text-white">{characterBrief.persona_card.name}</h4>
                  )}
                  {characterBrief.persona_card.personality_snapshot && (
                    <p className="text-sm text-brand-silver">{characterBrief.persona_card.personality_snapshot}</p>
                  )}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {characterBrief.persona_card.core_belief && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Core Belief:</span> <span className="text-white">{characterBrief.persona_card.core_belief}</span></div>
                    )}
                    {characterBrief.persona_card.superpower && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Superpower:</span> <span className="text-white">{characterBrief.persona_card.superpower}</span></div>
                    )}
                    {characterBrief.persona_card.fear && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Fear:</span> <span className="text-white">{characterBrief.persona_card.fear}</span></div>
                    )}
                    {characterBrief.persona_card.communication_style && (
                      <div className="p-2 rounded bg-white/5"><span className="text-brand-silver/50">Communication:</span> <span className="text-white">{characterBrief.persona_card.communication_style}</span></div>
                    )}
                  </div>
                  {characterBrief.persona_card.emotional_signature && characterBrief.persona_card.emotional_signature.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {characterBrief.persona_card.emotional_signature.map((e) => (
                        <span key={e} className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand-electric/20 text-brand-electric">{e}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Executive Summary */}
              {characterBrief.executive_summary && (
                <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                  <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Executive Summary</h4>
                  <div className="text-sm text-brand-silver prose prose-invert prose-sm max-w-none">
                    <MarkdownMessage content={characterBrief.executive_summary} />
                  </div>
                </div>
              )}

              {/* Positioning Alignment Score */}
              {characterBrief.positioning_alignment_score != null && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-white/5 border border-white/10">
                  <span className="text-xs text-brand-silver/60">Positioning Alignment:</span>
                  <span className={`text-sm font-bold ${scoreColor(characterBrief.positioning_alignment_score)}`}>
                    {Math.round(characterBrief.positioning_alignment_score)}%
                  </span>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-brand-silver/50 italic">No character brief data available.</p>
          )}
        </div>
      )}

      {/* Findings & Recommendations */}
      {findings && findings.length > 0 && (
        <div className="p-4 rounded-lg bg-white/5 border border-white/10">
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Key Findings</h4>
          <ul className="space-y-1">
            {findings.filter(f => typeof f === 'string' && f.trim()).map((f, i) => (
              <li key={i} className="text-xs text-brand-silver flex gap-1.5"><span className="text-brand-electric">&#8226;</span>{f}</li>
            ))}
          </ul>
        </div>
      )}
      {recommendations && recommendations.length > 0 && (
        <div className="p-4 rounded-lg bg-white/5 border border-white/10">
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Recommendations</h4>
          <ul className="space-y-1">
            {recommendations.filter(r => typeof r === 'string' && r.trim()).map((r, i) => (
              <li key={i} className="text-xs text-brand-silver flex gap-1.5"><span className="text-green-400">&#8594;</span>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function BrandPositioningSection({
  recommendedPositioning,
  positioningCandidates,
  canvas,
  perceptualMaps,
  differentiation,
  strategy,
  confidenceScore,
  sources,
  findings,
  recommendations,
}: {
  recommendedPositioning?: BPAPositioningStatement;
  positioningCandidates?: BPAPositioningStatement[];
  canvas?: BPACanvas;
  perceptualMaps?: BPAPerceptualMap[];
  differentiation?: BPADifferentiation;
  strategy?: BPAStrategy;
  confidenceScore?: number;
  sources?: SourceEntry[];
  findings?: string[];
  recommendations?: string[];
}) {
  const [activeTab, setActiveTab] = useState<'positioning' | 'canvas' | 'maps' | 'differentiation' | 'strategy'>('positioning');

  function scoreColor(score: number) {
    if (score >= 80) return 'text-green-400';
    if (score >= 60) return 'text-amber-400';
    return 'text-red-400';
  }

  function scoreBg(score: number) {
    if (score >= 80) return 'bg-green-400';
    if (score >= 60) return 'bg-amber-400';
    return 'bg-red-400';
  }

  const tabs = [
    { key: 'positioning' as const, label: 'Positioning' },
    { key: 'canvas' as const, label: 'Value Canvas' },
    { key: 'maps' as const, label: 'Perceptual Maps' },
    { key: 'differentiation' as const, label: 'Differentiation' },
    { key: 'strategy' as const, label: 'Strategy' },
  ];

  const scores = recommendedPositioning?.scores ?? {};
  const candidates = positioningCandidates ?? [];
  const maps = perceptualMaps ?? [];
  const pods = differentiation?.pods ?? [];
  const pops = differentiation?.pops ?? [];
  const rtbs = differentiation?.rtbs ?? [];
  const proofPoints = differentiation?.proof_points ?? [];

  return (
    <div className="space-y-6">
      {/* Header: title + confidence */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-bold text-white">Brand Positioning Strategy</h3>
        {confidenceScore != null && (() => {
          const pct = confidenceScore <= 1 ? Math.round(confidenceScore * 100) : Math.round(confidenceScore);
          return (
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold border ${pct >= 70 ? 'text-green-400 bg-green-400/10 border-green-400/30' : pct >= 40 ? 'text-amber-400 bg-amber-400/10 border-amber-400/30' : 'text-red-400 bg-red-400/10 border-red-400/30'}`}>
              Confidence: {pct}%
            </span>
          );
        })()}
      </div>

      {/* Tab navigation */}
      <div className="flex gap-1 overflow-x-auto border-b border-white/10 pb-px">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1.5 text-xs font-medium rounded-t-md transition-colors whitespace-nowrap ${activeTab === tab.key ? 'bg-brand-electric/20 text-brand-electric border-b-2 border-brand-electric' : 'text-brand-silver/60 hover:text-white hover:bg-white/5'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Positioning Tab ──────────────────────────────── */}
      {activeTab === 'positioning' && (
        <div className="space-y-4">
          {/* Recommended positioning */}
          {recommendedPositioning?.statement && (
            <div className="glass-card p-4 border border-brand-electric/30">
              <div className="flex items-center gap-2 mb-2">
                <span className="inline-flex items-center rounded-full bg-brand-electric/20 px-2 py-0.5 text-xs font-semibold text-brand-electric">
                  Recommended
                </span>
                {recommendedPositioning.framework_used && (
                  <span className="text-xs text-brand-silver/50 capitalize">
                    {recommendedPositioning.framework_used} framework
                  </span>
                )}
              </div>
              <p className="text-sm text-white leading-relaxed italic">
                &ldquo;{recommendedPositioning.statement}&rdquo;
              </p>
              {/* Score bars */}
              {Object.keys(scores).length > 0 && (
                <div className="mt-3 grid grid-cols-2 sm:grid-cols-5 gap-2">
                  {['clarity', 'differentiation', 'believability', 'memorability', 'overall'].map((dim) => {
                    const val = scores[dim];
                    if (val == null) return null;
                    return (
                      <div key={dim} className="text-center">
                        <div className="text-[10px] text-brand-silver/50 uppercase tracking-wider mb-1">{dim}</div>
                        <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${scoreBg(val)}`} style={{ width: `${val}%` }} />
                        </div>
                        <div className={`text-xs font-bold mt-0.5 ${scoreColor(val)}`}>{val}</div>
                      </div>
                    );
                  })}
                </div>
              )}
              {/* Details */}
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-brand-silver/70">
                {recommendedPositioning.target_audience && (
                  <div><span className="text-brand-silver/40">Target:</span> {recommendedPositioning.target_audience}</div>
                )}
                {recommendedPositioning.category && (
                  <div><span className="text-brand-silver/40">Category:</span> {recommendedPositioning.category}</div>
                )}
                {recommendedPositioning.need && (
                  <div><span className="text-brand-silver/40">Need:</span> {recommendedPositioning.need}</div>
                )}
                {recommendedPositioning.key_benefit && (
                  <div><span className="text-brand-silver/40">Key Benefit:</span> {recommendedPositioning.key_benefit}</div>
                )}
              </div>
            </div>
          )}

          {/* Alternative candidates */}
          {candidates.length > 1 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Alternative Positions ({candidates.length - 1})
              </h4>
              <div className="space-y-2">
                {candidates.slice(1).map((c, i) => (
                  <div key={i} className="glass-card p-3 border border-white/10">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-brand-silver/50 capitalize">
                        {c.framework_used ?? 'classic'} framework
                      </span>
                      {c.scores?.overall != null && (
                        <span className={`text-xs font-bold ${scoreColor(c.scores.overall)}`}>
                          {c.scores.overall}/100
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-brand-silver/80 italic">
                      &ldquo;{c.statement}&rdquo;
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Value Canvas Tab ────────────────────────────── */}
      {activeTab === 'canvas' && canvas && (
        <div className="space-y-4">
          {canvas.fit_score != null && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-brand-silver/50">Canvas Fit Score:</span>
              <span className={`text-sm font-bold ${scoreColor(canvas.fit_score)}`}>{canvas.fit_score}/100</span>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Customer Profile */}
            <div className="glass-card p-4 border border-purple-500/20">
              <h4 className="text-sm font-bold text-purple-400 mb-3">Customer Profile</h4>
              {canvas.customer_profile?.jobs && canvas.customer_profile.jobs.length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] text-brand-silver/40 uppercase tracking-wider mb-1">Jobs to be Done</div>
                  <ul className="space-y-0.5">
                    {canvas.customer_profile.jobs.map((j, i) => (
                      <li key={i} className="text-xs text-brand-silver/70 flex gap-1.5"><span className="text-purple-400/60">•</span>{j}</li>
                    ))}
                  </ul>
                </div>
              )}
              {canvas.customer_profile?.pains && canvas.customer_profile.pains.length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] text-brand-silver/40 uppercase tracking-wider mb-1">Pains</div>
                  <ul className="space-y-0.5">
                    {canvas.customer_profile.pains.map((p, i) => (
                      <li key={i} className="text-xs text-red-400/80 flex gap-1.5"><span className="text-red-400/40">•</span>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
              {canvas.customer_profile?.gains && canvas.customer_profile.gains.length > 0 && (
                <div>
                  <div className="text-[10px] text-brand-silver/40 uppercase tracking-wider mb-1">Gains</div>
                  <ul className="space-y-0.5">
                    {canvas.customer_profile.gains.map((g, i) => (
                      <li key={i} className="text-xs text-green-400/80 flex gap-1.5"><span className="text-green-400/40">•</span>{g}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Value Map */}
            <div className="glass-card p-4 border border-brand-electric/20">
              <h4 className="text-sm font-bold text-brand-electric mb-3">Value Map</h4>
              {canvas.value_map?.products && canvas.value_map.products.length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] text-brand-silver/40 uppercase tracking-wider mb-1">Products & Services</div>
                  <ul className="space-y-0.5">
                    {canvas.value_map.products.map((p, i) => (
                      <li key={i} className="text-xs text-brand-silver/70 flex gap-1.5"><span className="text-brand-electric/60">•</span>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
              {canvas.value_map?.pain_relievers && canvas.value_map.pain_relievers.length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] text-brand-silver/40 uppercase tracking-wider mb-1">Pain Relievers</div>
                  <ul className="space-y-0.5">
                    {canvas.value_map.pain_relievers.map((p, i) => (
                      <li key={i} className="text-xs text-green-400/80 flex gap-1.5"><span className="text-green-400/40">•</span>{p}</li>
                    ))}
                  </ul>
                </div>
              )}
              {canvas.value_map?.gain_creators && canvas.value_map.gain_creators.length > 0 && (
                <div>
                  <div className="text-[10px] text-brand-silver/40 uppercase tracking-wider mb-1">Gain Creators</div>
                  <ul className="space-y-0.5">
                    {canvas.value_map.gain_creators.map((g, i) => (
                      <li key={i} className="text-xs text-brand-electric/80 flex gap-1.5"><span className="text-brand-electric/40">•</span>{g}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
          {canvas.fit_analysis && (
            <div className="glass-card p-3 border border-white/10">
              <div className="text-[10px] text-brand-silver/40 uppercase tracking-wider mb-1">Fit Analysis</div>
              <p className="text-xs text-brand-silver/70">{canvas.fit_analysis}</p>
            </div>
          )}
        </div>
      )}

      {/* ── Perceptual Maps Tab ──────────────────────────── */}
      {activeTab === 'maps' && maps.length > 0 && (
        <div className="space-y-4">
          {maps.map((map, idx) => (
            <div key={map.map_id ?? idx} className="glass-card p-4 border border-white/10">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold text-white capitalize">
                    {(map.map_id ?? `map-${idx}`).replace(/_/g, ' ')}
                  </h4>
                  {map.is_primary_recommended && (
                    <span className="inline-flex items-center rounded-full bg-brand-electric/20 px-2 py-0.5 text-[10px] font-medium text-brand-electric">
                      Primary
                    </span>
                  )}
                </div>
                {map.differentiation_potential_score != null && (
                  <span className={`text-xs font-bold ${scoreColor(map.differentiation_potential_score)}`}>
                    Diff. Potential: {map.differentiation_potential_score}
                  </span>
                )}
              </div>
              {/* Axis labels */}
              <div className="text-[10px] text-brand-silver/40 flex justify-between mb-1">
                <span>{map.dimension_x ?? 'X Axis'} →</span>
                <span>↑ {map.dimension_y ?? 'Y Axis'}</span>
              </div>
              {/* Scatter plot area */}
              <div className="relative w-full aspect-square max-w-md mx-auto bg-white/5 rounded-lg border border-white/10 overflow-hidden">
                {/* Grid lines */}
                <div className="absolute inset-0" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)', backgroundSize: '25% 25%' }} />
                {/* Entities */}
                {(map.entities ?? []).map((entity, ei) => (
                  <div
                    key={ei}
                    className="absolute flex flex-col items-center"
                    style={{
                      left: `${entity.x ?? 50}%`,
                      bottom: `${entity.y ?? 50}%`,
                      transform: 'translate(-50%, 50%)',
                    }}
                  >
                    <div
                      className={`w-3 h-3 rounded-full border-2 ${entity.is_brand ? 'bg-brand-electric border-brand-electric shadow-lg shadow-brand-electric/40' : entity.is_target ? 'bg-green-400 border-green-400' : 'bg-white/60 border-white/40'}`}
                    />
                    <span className={`text-[9px] mt-0.5 whitespace-nowrap ${entity.is_brand ? 'text-brand-electric font-bold' : 'text-brand-silver/50'}`}>
                      {entity.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Differentiation Tab ──────────────────────────── */}
      {activeTab === 'differentiation' && (
        <div className="space-y-4">
          {differentiation?.overall_differentiation_score != null && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-brand-silver/50">Overall Differentiation:</span>
              <span className={`text-sm font-bold ${scoreColor(differentiation.overall_differentiation_score)}`}>
                {differentiation.overall_differentiation_score}/100
              </span>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Points of Difference */}
            {pods.length > 0 && (
              <div className="glass-card p-3 border border-green-500/20">
                <h4 className="text-xs font-semibold text-green-400 uppercase tracking-wider mb-2">
                  Points of Difference ({pods.length})
                </h4>
                <ul className="space-y-1">
                  {pods.map((pod, i) => (
                    <li key={i} className="text-xs text-brand-silver/70 flex gap-1.5">
                      <span className="text-green-400/60 mt-0.5">◆</span>
                      {typeof pod === 'string' ? pod : JSON.stringify(pod)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {/* Points of Parity */}
            {pops.length > 0 && (
              <div className="glass-card p-3 border border-white/10">
                <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                  Points of Parity ({pops.length})
                </h4>
                <ul className="space-y-1">
                  {pops.map((pop, i) => (
                    <li key={i} className="text-xs text-brand-silver/60 flex gap-1.5">
                      <span className="text-brand-silver/30 mt-0.5">○</span>
                      {typeof pop === 'string' ? pop : JSON.stringify(pop)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {/* RTBs */}
          {rtbs.length > 0 && (
            <div className="glass-card p-3 border border-brand-electric/20">
              <h4 className="text-xs font-semibold text-brand-electric uppercase tracking-wider mb-2">
                Reasons to Believe ({rtbs.length})
              </h4>
              <ul className="space-y-1">
                {rtbs.map((rtb, i) => (
                  <li key={i} className="text-xs text-brand-silver/70 flex gap-1.5">
                    <span className="text-brand-electric/60 mt-0.5">✓</span>
                    {typeof rtb === 'string' ? rtb : JSON.stringify(rtb)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {/* Proof Points */}
          {proofPoints.length > 0 && (
            <div className="glass-card p-3 border border-purple-500/20">
              <h4 className="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-2">
                Proof Points ({proofPoints.length})
              </h4>
              <ul className="space-y-1">
                {proofPoints.map((pp, i) => (
                  <li key={i} className="text-xs text-brand-silver/70 flex gap-1.5">
                    <span className="text-purple-400/60 mt-0.5">▸</span>
                    {typeof pp === 'string' ? pp : JSON.stringify(pp)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ── Strategy Tab ─────────────────────────────────── */}
      {activeTab === 'strategy' && strategy && (
        <div className="space-y-4">
          {strategy.executive_summary && (
            <div className="glass-card p-4 border border-white/10">
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Executive Summary
              </h4>
              <p className="text-sm text-brand-silver/80 leading-relaxed">{strategy.executive_summary}</p>
            </div>
          )}
          {/* Strategic Pillars */}
          {strategy.strategic_pillars && strategy.strategic_pillars.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Strategic Pillars
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {strategy.strategic_pillars.map((pillar, i) => (
                  <div key={i} className="glass-card p-3 border border-brand-electric/10">
                    <div className="text-sm font-semibold text-white mb-1">{pillar.name}</div>
                    <p className="text-xs text-brand-silver/60">{pillar.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Implementation Timeline */}
          {strategy.implementation_timeline && strategy.implementation_timeline.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Implementation Roadmap
              </h4>
              <div className="space-y-2">
                {strategy.implementation_timeline.map((phase, i) => (
                  <div key={i} className="glass-card p-3 border border-white/10">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-semibold text-white">{phase.phase}</span>
                      {phase.timeframe && (
                        <span className="text-[10px] text-brand-silver/40">{phase.timeframe}</span>
                      )}
                    </div>
                    {phase.actions && phase.actions.length > 0 && (
                      <ul className="space-y-0.5">
                        {phase.actions.map((a, j) => (
                          <li key={j} className="text-xs text-brand-silver/60 flex gap-1.5">
                            <span className="text-brand-electric/40">→</span>{a}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Success Metrics */}
          {strategy.success_metrics && strategy.success_metrics.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Success Metrics
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left text-brand-silver/40 font-medium py-1 pr-4">Metric</th>
                      <th className="text-left text-brand-silver/40 font-medium py-1 pr-4">Target</th>
                      <th className="text-left text-brand-silver/40 font-medium py-1">Timeframe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {strategy.success_metrics.map((m, i) => (
                      <tr key={i} className="border-b border-white/5">
                        <td className="py-1.5 pr-4 text-white">{m.metric}</td>
                        <td className="py-1.5 pr-4 text-brand-electric">{m.target}</td>
                        <td className="py-1.5 text-brand-silver/50">{m.timeframe}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Sources */}
      {sources && sources.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Sources ({sources.length})
          </h4>
          <div className="space-y-1">
            {sources.filter((s) => s.title || s.url).map((s, i) => (
              <div key={i} className="text-xs text-brand-silver/50">
                {(s.url && /^https?:\/\//i.test(s.url)) ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-brand-electric/70 hover:underline">
                    {s.title || s.url}
                  </a>
                ) : (
                  <span>{s.title || '-'}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Findings & Recommendations */}
      {findings && findings.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Key Findings</h4>
          {findings.map((f, i) => (
            <div key={i} className="mb-1"><MarkdownMessage content={f} /></div>
          ))}
        </section>
      )}
      {recommendations && recommendations.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Recommendations</h4>
          {recommendations.map((r, i) => (
            <div key={i} className="mb-1"><MarkdownMessage content={r} /></div>
          ))}
        </section>
      )}
    </div>
  );
}

function VoiceOfCustomerSection({
  vocHealthScore,
  operatingMode,
  dataCoverageScore,
  sentiment,
  themes,
  npsAnalysis,
  painPointMatrix,
  strategyBridge,
  sources,
  confidenceScore,
  findings,
  recommendations,
}: {
  vocHealthScore?: number;
  operatingMode?: string;
  dataCoverageScore?: number;
  sentiment?: VoCSentimentFELocal;
  themes?: VoCThemeMapLocal;
  npsAnalysis?: VoCNPSLocal;
  painPointMatrix?: { pain_points?: VoCPainPointLocal[]; methodology?: string };
  strategyBridge?: VoCStrategyBridgeLocal;
  sources?: SourceEntry[];
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  const [expandedTheme, setExpandedTheme] = useState<string | null>(null);

  function healthScoreColor(score: number) {
    if (score >= 70) return 'text-green-400 bg-green-400/10 border-green-400/30';
    if (score >= 40) return 'text-amber-400 bg-amber-400/10 border-amber-400/30';
    return 'text-red-400 bg-red-400/10 border-red-400/30';
  }

  function severityColor(severity: number) {
    if (severity >= 7) return 'text-red-400';
    if (severity >= 4) return 'text-amber-400';
    return 'text-green-400';
  }

  function sentimentBar(pos: number, neu: number, neg: number) {
    const total = pos + neu + neg;
    if (total === 0) return null;
    const pPct = (pos / total) * 100;
    const nPct = (neu / total) * 100;
    return (
      <div className="flex w-full h-2 rounded-full overflow-hidden bg-white/10">
        <div className="bg-green-400 h-full" style={{ width: `${pPct}%` }} />
        <div className="bg-amber-400 h-full" style={{ width: `${nPct}%` }} />
        <div className="bg-red-400 h-full flex-1" />
      </div>
    );
  }

  const safeArr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
  const safeObj = (v: unknown): Record<string, unknown> =>
    v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
  const safeNum = (v: unknown): number | undefined => {
    if (typeof v === 'number') return v;
    if (typeof v === 'string') { const n = Number(v); return isNaN(n) ? undefined : n; }
    return undefined;
  };

  const overallSentiment = sentiment != null && typeof sentiment === 'object' && !Array.isArray(sentiment) ? (sentiment as VoCSentimentFELocal)?.overall_sentiment : undefined;
  const emotionProfile = sentiment != null && typeof sentiment === 'object' && !Array.isArray(sentiment) && sentiment.emotion_profile != null && typeof sentiment.emotion_profile === 'object' && !Array.isArray(sentiment.emotion_profile) ? sentiment.emotion_profile : undefined;
  const channelSentiments = safeArr(sentiment != null && typeof sentiment === 'object' && !Array.isArray(sentiment) ? (sentiment as VoCSentimentFELocal)?.channel_sentiments : undefined) as Array<{
    channel: string; provenance?: string; sentiment?: { positive?: number; neutral?: number; negative?: number }; feedback_count?: number; confidence?: number;
  }>;
  const themeClusters = safeArr(themes != null && typeof themes === 'object' && !Array.isArray(themes) ? (themes as VoCThemeMapLocal)?.themes : undefined) as VoCThemeClusterLocal[];
  const painPoints = safeArr(painPointMatrix != null && typeof painPointMatrix === 'object' && !Array.isArray(painPointMatrix) ? ((painPointMatrix as Record<string, unknown>)?.pain_points ?? (painPointMatrix as Record<string, unknown>)?.ranked_pain_points) : undefined) as VoCPainPointLocal[];
  const nps = npsAnalysis != null && typeof npsAnalysis === 'object' && !Array.isArray(npsAnalysis) ? npsAnalysis : undefined;
  const rawActiveNps = nps?.nps_available ? nps?.current_nps : nps?.proxy_nps;
  const activeNps = rawActiveNps != null && typeof rawActiveNps === 'object' && !Array.isArray(rawActiveNps) ? rawActiveNps : undefined;
  const execSummary = typeof strategyBridge === 'object' && strategyBridge != null && typeof (strategyBridge as VoCStrategyBridgeLocal)?.executive_summary === 'string' ? (strategyBridge as VoCStrategyBridgeLocal).executive_summary : undefined;
  const crossAgentInsights = safeObj(typeof strategyBridge === 'object' && strategyBridge != null ? (strategyBridge as VoCStrategyBridgeLocal)?.cross_agent_insights : undefined) as Record<string, string>;
  const stratRecs = safeArr(typeof strategyBridge === 'object' && strategyBridge != null ? (strategyBridge as VoCStrategyBridgeLocal)?.strategic_recommendations ?? recommendations : recommendations) as string[];

  return (
    <div className="space-y-6">
      {/* VoC Health Score + Operating Mode */}
      <div className="flex flex-wrap items-center gap-3">
        {vocHealthScore != null && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
              VoC Health
            </span>
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold border ${healthScoreColor(vocHealthScore)}`}>
              {vocHealthScore}/100
            </span>
          </div>
        )}
        {operatingMode && (
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${operatingMode === 'full' ? 'bg-green-400/20 text-green-400' : 'bg-amber-400/20 text-amber-400'}`}>
            {operatingMode === 'full' ? 'Full Mode' : 'External-Only'}
          </span>
        )}
        {dataCoverageScore != null && (
          <span className="text-xs text-brand-silver/50">
            Data coverage: {Math.round(dataCoverageScore * 100)}%
          </span>
        )}
        {confidenceScore != null && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
              Confidence
            </span>
            <span className="inline-flex items-center rounded-full bg-brand-electric/20 px-3 py-1 text-sm font-bold text-brand-electric">
              {typeof confidenceScore === 'number' ? `${Math.round(confidenceScore * 100)}%` : confidenceScore}
            </span>
          </div>
        )}
      </div>

      {/* Strategy Bridge Executive Summary */}
      {execSummary && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Executive Summary
          </h4>
          <div className="bg-white/5 rounded-lg p-4 border border-white/10">
            <MarkdownMessage content={execSummary} />
          </div>
        </section>
      )}

      {/* Sentiment Analysis */}
      {overallSentiment && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Sentiment Analysis
          </h4>
          <div className="space-y-4">
            {/* Overall distribution bar */}
            <div className="bg-white/5 rounded-lg p-4 border border-white/10">
              <h5 className="text-xs text-brand-silver/50 uppercase mb-2">Overall Distribution</h5>
              {sentimentBar(
                overallSentiment.positive ?? 0,
                overallSentiment.neutral ?? 0,
                overallSentiment.negative ?? 0,
              )}
              <div className="flex justify-between mt-2 text-xs text-brand-silver/60">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
                  Positive {((overallSentiment.positive ?? 0) * 100).toFixed(0)}%
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
                  Neutral {((overallSentiment.neutral ?? 0) * 100).toFixed(0)}%
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-red-400 inline-block" />
                  Negative {((overallSentiment.negative ?? 0) * 100).toFixed(0)}%
                </span>
              </div>
              {sentiment?.trend_direction && (
                <p className="text-xs text-brand-silver/50 mt-2">
                  Trend: {sentiment.trend_direction}
                </p>
              )}
            </div>

            {/* Emotion Profile */}
            {emotionProfile && Object.keys(emotionProfile).length > 0 && (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <h5 className="text-xs text-brand-silver/50 uppercase mb-2">Emotion Profile</h5>
                <div className="grid grid-cols-4 gap-2">
                  {Object.entries(emotionProfile)
                    .filter(([, v]) => typeof v === 'number' && v > 0)
                    .sort(([, a], [, b]) => (b as number) - (a as number))
                    .map(([emotion, value]) => (
                      <div key={emotion} className="text-center">
                        <div className="text-[10px] text-brand-silver/50 capitalize">{emotion}</div>
                        <div className="w-full bg-white/10 rounded-full h-1.5 mt-0.5">
                          <div
                            className="bg-brand-electric rounded-full h-1.5"
                            style={{ width: `${(value as number) * 100}%` }}
                          />
                        </div>
                        <div className="text-[10px] text-brand-silver/60 mt-0.5">
                          {((value as number) * 100).toFixed(0)}%
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Per-channel breakdown */}
            {channelSentiments.length > 0 && (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <h5 className="text-xs text-brand-silver/50 uppercase mb-2">
                  Channel Breakdown ({channelSentiments.length})
                </h5>
                <div className="space-y-3">
                  {channelSentiments.map((ch, i) => (
                    <div key={i}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-white capitalize">
                          {ch.channel?.replace(/_/g, ' ')}
                        </span>
                        <div className="flex items-center gap-2">
                          {ch.provenance && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${ch.provenance === 'internal' ? 'bg-blue-400/20 text-blue-400' : 'bg-purple-400/20 text-purple-400'}`}>
                              {ch.provenance}
                            </span>
                          )}
                          {ch.feedback_count != null && (
                            <span className="text-[10px] text-brand-silver/40">
                              {ch.feedback_count} items
                            </span>
                          )}
                        </div>
                      </div>
                      {ch.sentiment && sentimentBar(
                        ch.sentiment.positive ?? 0,
                        ch.sentiment.neutral ?? 0,
                        ch.sentiment.negative ?? 0,
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Theme Clusters */}
      {themeClusters.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Theme Clusters ({themeClusters.length})
            {themes?.total_feedback_analyzed != null && (
              <span className="font-normal ml-2 text-brand-silver/40">
                {themes.total_feedback_analyzed} feedback items analyzed
              </span>
            )}
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {themeClusters.map((theme, i) => {
              const key = theme.theme_slug ?? `theme-${i}`;
              const isExpanded = expandedTheme === key;
              return (
                <div
                  key={key}
                  className="bg-white/5 rounded-lg p-4 border border-white/10 cursor-pointer hover:border-white/20 transition-colors"
                  onClick={() => setExpandedTheme(isExpanded ? null : key)}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold text-white truncate mr-2">
                      {theme.theme_name || theme.theme_slug}
                    </span>
                    <div className="flex items-center gap-2 shrink-0">
                      {theme.feedback_count != null && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-brand-silver/60">
                          {theme.feedback_count} mentions
                        </span>
                      )}
                      {safeNum(theme.severity_score) != null && (
                        <span className={`text-xs font-bold ${severityColor(safeNum(theme.severity_score) as number)}`}>
                          {(safeNum(theme.severity_score) as number).toFixed(1)}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Sentiment bar for this theme */}
                  {theme.sentiment && sentimentBar(
                    theme.sentiment.positive ?? 0,
                    theme.sentiment.neutral ?? 0,
                    theme.sentiment.negative ?? 0,
                  )}

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-white/10 space-y-2">
                      {/* Sub-themes */}
                      {Array.isArray(theme.sub_themes) && theme.sub_themes.length > 0 && (
                        <div>
                          <span className="text-[10px] text-brand-silver/50 uppercase">Sub-themes</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {theme.sub_themes.filter((st): st is NonNullable<typeof st> => st != null && typeof st === 'object').map((st, si) => (
                              <span key={si} className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-brand-silver/70">
                                {st.name}{st.feedback_count ? ` (${st.feedback_count})` : ''}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {/* Representative quotes */}
                      {Array.isArray(theme.representative_quotes) && theme.representative_quotes.length > 0 && (
                        <div>
                          <span className="text-[10px] text-brand-silver/50 uppercase">Quotes</span>
                          {theme.representative_quotes.slice(0, 3).map((q, qi) => (
                            <p key={qi} className="text-xs text-brand-silver/60 italic mt-0.5">&ldquo;{q}&rdquo;</p>
                          ))}
                        </div>
                      )}
                      {theme.competitor_correlation && (
                        <p className="text-xs text-brand-silver/50">
                          Competitor correlation: {theme.competitor_correlation}
                        </p>
                      )}
                      {theme.market_context && (
                        <p className="text-xs text-brand-silver/50">
                          Market context: {theme.market_context}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* NPS Analysis */}
      {nps && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            NPS Analysis
          </h4>
          {activeNps ? (
            <div className="bg-white/5 rounded-lg p-4 border border-white/10">
              <div className="flex items-center gap-4 mb-3">
                <div className="text-center">
                  <div className="text-[10px] text-brand-silver/50 uppercase">
                    {nps.nps_available ? 'NPS Score' : 'Proxy NPS'}
                  </div>
                  <div className={`text-2xl font-bold ${(safeNum(activeNps.nps_score) ?? 0) >= 50 ? 'text-green-400' : (safeNum(activeNps.nps_score) ?? 0) >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
                    {safeNum(activeNps.nps_score) != null ? `${(safeNum(activeNps.nps_score) as number) >= 0 ? '+' : ''}${(safeNum(activeNps.nps_score) as number).toFixed(0)}` : 'N/A'}
                  </div>
                </div>
                <div className="flex-1 grid grid-cols-3 gap-2 text-center">
                  <div>
                    <div className="text-[10px] text-brand-silver/50">Promoters</div>
                    <div className="text-sm font-bold text-green-400">{activeNps.promoters ?? 0}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-brand-silver/50">Passives</div>
                    <div className="text-sm font-bold text-amber-400">{activeNps.passives ?? 0}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-brand-silver/50">Detractors</div>
                    <div className="text-sm font-bold text-red-400">{activeNps.detractors ?? 0}</div>
                  </div>
                </div>
              </div>
              {!nps.nps_available && (
                <p className="text-xs text-amber-400/70 italic">
                  Estimated from external feedback — connect Odoo for actual NPS data
                </p>
              )}
              {nps.data_source && (
                <p className="text-xs text-brand-silver/40 mt-1">Source: {nps.data_source}</p>
              )}
              {Array.isArray(nps.drivers) && nps.drivers.length > 0 && (
                <div className="mt-3">
                  <span className="text-[10px] text-brand-silver/50 uppercase">NPS Drivers</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {nps.drivers.map((d, i) => {
                      const label = typeof d === 'string' ? d : (d as Record<string, unknown>)?.driver ?? JSON.stringify(d);
                      return (
                        <span key={String(label) + i} className="text-xs px-2 py-0.5 rounded-full bg-green-400/10 text-green-400/80">
                          {String(label)}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
              {Array.isArray(nps.detractor_themes) && nps.detractor_themes.length > 0 && (
                <div className="mt-2">
                  <span className="text-[10px] text-brand-silver/50 uppercase">Detractor Themes</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {nps.detractor_themes.map((d, i) => {
                      const label = typeof d === 'string' ? d : (d as Record<string, unknown>)?.theme ?? JSON.stringify(d);
                      return (
                        <span key={String(label) + i} className="text-xs px-2 py-0.5 rounded-full bg-red-400/10 text-red-400/80">
                          {String(label)}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white/5 rounded-lg p-4 border border-white/10 text-center">
              <p className="text-sm text-brand-silver/50">NPS data not available</p>
              <p className="text-xs text-brand-silver/40 mt-1">
                Connect Odoo Helpdesk surveys for NPS tracking
              </p>
            </div>
          )}
        </section>
      )}

      {/* Pain Point Priority Matrix */}
      {painPoints.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Pain Point Priority Matrix ({painPoints.length})
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-brand-silver/50 border-b border-white/10">
                  <th className="text-left py-2 px-3">#</th>
                  <th className="text-left py-2 px-3">Pain Point</th>
                  <th className="text-center py-2 px-3">Severity</th>
                  <th className="text-center py-2 px-3">Frequency</th>
                  <th className="text-left py-2 px-3">Affected Personas</th>
                  <th className="text-left py-2 px-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {painPoints.map((pp, i) => (
                  <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-brand-silver/40">{i + 1}</td>
                    <td className="py-2 px-3 text-white font-medium">{pp.name}</td>
                    <td className="py-2 px-3 text-center">
                      <span className={`font-bold ${severityColor(safeNum(pp.severity) ?? 0)}`}>
                        {safeNum(pp.severity) != null ? (safeNum(pp.severity) as number).toFixed(1) : '-'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-center text-brand-silver/70">
                      {pp.frequency ?? 0}
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex flex-wrap gap-1">
                        {Array.isArray(pp.persona_impact) && pp.persona_impact.slice(0, 3).map((p) => (
                          <span key={p} className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-brand-silver/60">
                            {p}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 px-3 text-brand-silver/60 max-w-[200px] truncate">
                      {pp.recommended_action}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Cross-Agent Insights */}
      {crossAgentInsights && Object.keys(crossAgentInsights).length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
            Cross-Agent Insights
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(crossAgentInsights).map(([agent, insight]) => (
              <div key={agent} className="bg-white/5 rounded-lg p-3 border border-white/10">
                <span className="text-[10px] text-brand-electric/60 uppercase">
                  {agent.replace(/_/g, ' ')}
                </span>
                <p className="text-xs text-brand-silver/70 mt-1">{insight}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Strategic Recommendations */}
      {stratRecs.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Strategic Recommendations
          </h4>
          {stratRecs.map((r, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={typeof r === 'string' ? r : JSON.stringify(r)} />
            </div>
          ))}
        </section>
      )}

      {/* Odoo Onboarding Recommendation */}
      {strategyBridge?.odoo_onboarding_recommendation && (
        <section>
          <div className="bg-blue-400/5 rounded-lg p-4 border border-blue-400/20">
            <h4 className="font-heading text-xs font-semibold text-blue-400/80 uppercase tracking-wider mb-2">
              Odoo Onboarding Recommendation
            </h4>
            <p className="text-sm text-brand-silver/70">
              {strategyBridge.odoo_onboarding_recommendation}
            </p>
          </div>
        </section>
      )}

      {/* Findings */}
      {findings && findings.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Key Findings
          </h4>
          {findings.map((f, i) => (
            <div key={i} className="mb-2">
              <MarkdownMessage content={f} />
            </div>
          ))}
        </section>
      )}

      {/* Sources */}
      {sources && sources.length > 0 && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Sources ({sources.length})
          </h4>
          <div className="space-y-1 max-h-60 overflow-y-auto rounded-lg border border-white/5 p-2">
            {sources.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <ExternalLink className="w-3 h-3 text-brand-silver/40 shrink-0" />
                {s.url ? (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-electric/80 hover:text-brand-electric truncate"
                  >
                    {s.title || s.url}
                  </a>
                ) : (
                  <span className="text-brand-silver/60">{s.title || '-'}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ── Campaign Architecture Agent (CAA) Types ──────────────────────

interface CAAFunnelStage {
  stage?: string;
  meta_objective?: string;
  budget_pct?: number;
  description?: string;
}

interface CAAFunnelMap {
  stages?: CAAFunnelStage[];
}

interface CAATargetingSpec {
  ad_set_name?: string;
  funnel_stage?: string;
  demographics?: Record<string, unknown>;
  interests?: string[];
  behaviors?: string[];
  custom_audiences?: string[];
  lookalike_audiences?: string[];
  exclusions?: string[];
  estimated_audience_size?: number;
}

interface CAAAdSet {
  name?: string;
  funnel_stage?: string;
  objective?: string;
  targeting?: CAATargetingSpec;
  placements?: string[];
  daily_budget?: number;
  bid_strategy?: string;
  optimization_goal?: string;
  creative_briefs?: Array<Record<string, unknown>>;
}

interface CAABlueprint {
  campaign_name?: string;
  campaign_objective?: string;
  special_ad_category?: string;
  buying_type?: string;
  daily_budget?: number;
  bid_strategy?: string;
  cbo_enabled?: boolean;
  ad_sets?: CAAAdSet[];
}

interface CAATestVariant {
  variable?: string;
  variants?: string[];
  sample_size_per_variant?: number;
  duration_days?: number;
  success_metric?: string;
  priority?: string;
}

interface CAATestPlan {
  tests?: CAATestVariant[];
  total_testing_budget_pct?: number;
  total_variants?: number;
}

interface CAAPerformanceProjections {
  estimated_reach?: number;
  estimated_impressions?: number;
  estimated_clicks?: number;
  estimated_conversions?: number;
  projected_roas?: number;
  confidence_range?: Record<string, number>;
}

interface CAARiskAssessment {
  risks?: Array<{ category?: string; description?: string; severity?: string; mitigation?: string }>;
}

interface CAACreativeBrief {
  ad_set_name?: string;
  format?: string;
  headline?: string;
  primary_text?: string;
  cta?: string;
  visual_direction?: string;
}

// ── Creative Generation (CGA) Types ──────────────────────────────
interface CGAGeneratedImage {
  ad_set_name?: string;
  variant_id?: string;
  aspect_ratio?: string;
  gcs_url?: string;
  thumbnail_url?: string;
  image_generated?: boolean;
  prompt_used?: string;
  provider?: string;
  cost_usd?: number;
  generation_time_ms?: number;
}

interface CGAHookVariant {
  ad_set_name?: string;
  hooks?: Array<{
    hook_text?: string;
    hook_pattern?: string;
    scroll_stop_power?: number;
    char_count?: number;
    rationale?: string;
  }>;
}

interface CGACopySet {
  ad_set_name?: string;
  variants?: Array<{
    variant_id?: string;
    short?: { text?: string; char_count?: number };
    medium?: { text?: string; char_count?: number };
    long?: { text?: string; char_count?: number };
    emotional_appeal?: string;
    key_message?: string;
  }>;
}

interface CGACTASet {
  ad_set_name?: string;
  cta_variants?: Array<{
    cta_button?: string;
    cta_text?: string;
    urgency_score?: number;
    clarity_score?: number;
    rationale?: string;
  }>;
}

interface CGAComplianceResult {
  ad_set_name?: string;
  variant_id?: string;
  copy_type?: string;
  copy_text?: string;
  status?: string;
  violations?: Array<{
    rule?: string;
    severity?: string;
    description?: string;
    suggested_fix?: string;
  }>;
}

interface CGACreativeUnit {
  ad_set_name?: string;
  unit_id?: string;
  image_variant_id?: string;
  image_aspect_ratio?: string;
  image_gcs_url?: string;
  headline?: string;
  primary_text?: string;
  copy_length?: string;
  cta_button?: string;
  cta_text?: string;
  ad_format?: string;
  target_placement?: string;
  image_copy_coherence?: number;
  coherence_rationale?: string;
}

interface CGAAdSetPackage {
  ad_set_name?: string;
  persona?: string;
  funnel_stage?: string;
  images?: CGAGeneratedImage[];
  hooks?: CGAHookVariant[];
  primary_copy?: CGACopySet[];
  ctas?: CGACTASet[];
  creative_units?: CGACreativeUnit[];
  compliance_results?: CGAComplianceResult[];
  ad_set_quality_score?: number;
}

interface CGACreativePackage {
  campaign_id?: string;
  brand_name?: string;
  total_images_generated?: number;
  total_images_refined?: number;
  image_gen_cost_usd?: number;
  compliance_pass_rate?: number;
  creative_quality_score?: number;
  confidence_score?: number;
}

// ── Creative Generation Section Component ─────────────────────────
function CreativeGenerationSection({
  creativePackage,
  adSetPackages,
  adUnits,
  generatedImages,
  hooks,
  copyVariants,
  ctas,
  complianceResults,
  totalImagesGenerated,
  imageGenCostUsd,
  compliancePassRate,
  creativeQualityScore,
  confidenceScore,
  imageGenFailed,
  findings,
  recommendations,
}: {
  creativePackage?: CGACreativePackage;
  adSetPackages?: CGAAdSetPackage[];
  adUnits?: CGACreativeUnit[];
  generatedImages?: CGAGeneratedImage[];
  hooks?: CGAHookVariant[];
  copyVariants?: CGACopySet[];
  ctas?: CGACTASet[];
  complianceResults?: CGAComplianceResult[];
  totalImagesGenerated?: number;
  imageGenCostUsd?: number;
  compliancePassRate?: number;
  creativeQualityScore?: number;
  confidenceScore?: number;
  imageGenFailed?: boolean;
  findings?: string[];
  recommendations?: string[];
}) {
  const [activeTab, setActiveTab] = useState<'overview' | 'gallery' | 'copy' | 'compliance' | 'units'>('overview');
  const [zoomedImage, setZoomedImage] = useState<CGAGeneratedImage | null>(null);

  const tabs = [
    { key: 'overview' as const, label: 'Overview' },
    { key: 'gallery' as const, label: 'Creative Gallery' },
    { key: 'copy' as const, label: 'Ad Copy' },
    { key: 'compliance' as const, label: 'Compliance' },
    { key: 'units' as const, label: 'Ad Units' },
  ];

  const imgCount = totalImagesGenerated ?? creativePackage?.total_images_generated ?? 0;
  const cost = imageGenCostUsd ?? creativePackage?.image_gen_cost_usd ?? 0;
  const passRate = compliancePassRate ?? creativePackage?.compliance_pass_rate ?? 0;
  const quality = creativeQualityScore ?? creativePackage?.creative_quality_score ?? 0;
  const confidence = confidenceScore ?? creativePackage?.confidence_score ?? 0;
  const allUnits = adUnits ?? [];
  const allImages = generatedImages ?? [];
  const allHooks = hooks ?? [];
  const allCopy = copyVariants ?? [];
  const allCtas = ctas ?? [];
  const allCompliance = complianceResults ?? [];
  const packages = adSetPackages ?? [];

  return (
    <section className="space-y-4">
      <h4 className="font-heading text-sm font-semibold text-white flex items-center gap-2">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-brand-electric/20 text-brand-electric text-xs font-bold">
          CG
        </span>
        Creative Generation
        {confidence > 0 && (
          <span className="ml-2 text-xs font-normal text-brand-silver/60">
            Confidence: {(confidence * 100).toFixed(0)}%
          </span>
        )}
      </h4>

      {imageGenFailed && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 text-xs text-amber-400">
          Image generation failed — creative package contains copy only.
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-1 bg-white/5 rounded-lg p-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-brand-electric/20 text-brand-electric'
                : 'text-brand-silver/60 hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-4">
          {/* KPI Grid */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: 'Images Generated', value: imgCount.toString(), color: 'text-brand-electric' },
              { label: 'Image Cost', value: `$${cost.toFixed(2)}`, color: 'text-emerald-400' },
              { label: 'Compliance Rate', value: `${(passRate * 100).toFixed(0)}%`, color: passRate >= 0.9 ? 'text-emerald-400' : passRate >= 0.7 ? 'text-amber-400' : 'text-red-400' },
              { label: 'Creative Quality', value: `${(quality * 100).toFixed(0)}%`, color: 'text-brand-electric' },
              { label: 'Ad Units', value: allUnits.length.toString(), color: 'text-violet-400' },
            ].map((kpi, i) => (
              <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10">
                <div className="text-[10px] font-medium text-brand-silver/50 uppercase tracking-wider">{kpi.label}</div>
                <div className={`text-lg font-bold ${kpi.color}`}>{kpi.value}</div>
              </div>
            ))}
          </div>

          {/* Ad Set Packages summary */}
          {packages.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Ad Set Packages ({packages.length})
              </h5>
              <div className="space-y-2">
                {packages.map((pkg, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10 flex items-center justify-between">
                    <div>
                      <span className="text-sm font-medium text-white">{pkg.ad_set_name ?? `Ad Set ${i + 1}`}</span>
                      <span className="ml-2 text-xs text-brand-silver/50">{pkg.funnel_stage?.toUpperCase()}</span>
                      {pkg.persona && <span className="ml-2 text-xs text-brand-silver/40">— {pkg.persona}</span>}
                    </div>
                    {pkg.ad_set_quality_score != null && (
                      <span className="text-xs font-bold text-brand-electric">
                        {(pkg.ad_set_quality_score * 100).toFixed(0)}% quality
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Findings + Recommendations */}
          {findings && findings.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Key Findings</h5>
              <ul className="space-y-1">
                {findings.filter((f) => typeof f === 'string' && f.trim()).map((f, i) => (
                  <li key={i} className="text-xs text-brand-silver/80 pl-3 border-l-2 border-brand-electric/30">{f}</li>
                ))}
              </ul>
            </div>
          )}
          {recommendations && recommendations.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Recommendations</h5>
              <ul className="space-y-1">
                {recommendations.filter((r) => typeof r === 'string' && r.trim()).map((r, i) => (
                  <li key={i} className="text-xs text-brand-silver/80 pl-3 border-l-2 border-emerald-500/30">{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Gallery Tab */}
      {activeTab === 'gallery' && (
        <div className="space-y-4">
          {allImages.length === 0 ? (
            <p className="text-xs text-brand-silver/50">No images generated.</p>
          ) : (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
                Generated Images ({allImages.length})
              </h5>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {allImages.map((img, i) => {
                  const imgSrc = img.gcs_url || img.thumbnail_url || '';
                  const hasImage = imgSrc && (imgSrc.startsWith('data:') || imgSrc.startsWith('http'));
                  return (
                    <div key={i} className="bg-white/5 rounded-lg border border-white/10 overflow-hidden">
                      {hasImage ? (
                        <button
                          type="button"
                          onClick={() => setZoomedImage(img)}
                          className="w-full h-40 bg-black/20 flex items-center justify-center overflow-hidden cursor-zoom-in"
                        >
                          <img
                            src={imgSrc}
                            alt={`${img.ad_set_name} ${img.aspect_ratio}`}
                            className="h-full w-full object-cover"
                          />
                        </button>
                      ) : (
                        <div className="h-40 bg-gradient-to-br from-brand-electric/10 to-violet-500/10 flex items-center justify-center">
                          <span className="text-xs text-brand-silver/40">
                            {img.image_generated ? 'Generated (configure GCS to display)' : 'Placeholder'} · {img.aspect_ratio ?? '1:1'}
                          </span>
                        </div>
                      )}
                      <div className="p-2 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-white">{img.ad_set_name}</span>
                          <span className="text-[10px] text-brand-silver/40">{img.variant_id} / {img.aspect_ratio}</span>
                        </div>
                        <div className="flex items-center justify-between text-[10px] text-brand-silver/40">
                          <span>{img.provider ?? 'nano_banana_2'}</span>
                          {img.cost_usd != null && <span>${img.cost_usd.toFixed(3)}</span>}
                        </div>
                        {img.prompt_used && (
                          <p className="text-[10px] text-brand-silver/30 line-clamp-2">{img.prompt_used}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Zoom modal */}
          {zoomedImage && (() => {
            const zoomSrc = zoomedImage.gcs_url || zoomedImage.thumbnail_url || '';
            return (
              <div
                className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 cursor-zoom-out"
                onClick={() => setZoomedImage(null)}
              >
                <div className="relative max-w-4xl max-h-[90vh] w-full flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    onClick={() => setZoomedImage(null)}
                    className="absolute -top-8 right-0 text-white/60 hover:text-white text-sm"
                  >
                    Close
                  </button>
                  {zoomSrc && (
                    <img
                      src={zoomSrc}
                      alt={`${zoomedImage.ad_set_name} ${zoomedImage.aspect_ratio}`}
                      className="max-h-[80vh] max-w-full object-contain rounded-lg"
                    />
                  )}
                  <div className="mt-3 text-center space-y-1">
                    <p className="text-sm font-medium text-white">{zoomedImage.ad_set_name} — {zoomedImage.variant_id}</p>
                    <p className="text-xs text-brand-silver/60">{zoomedImage.aspect_ratio} · {zoomedImage.provider ?? 'nano_banana_2'}</p>
                    {zoomedImage.prompt_used && (
                      <p className="text-xs text-brand-silver/40 max-w-lg">{zoomedImage.prompt_used}</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* Copy Tab */}
      {activeTab === 'copy' && (
        <div className="space-y-4">
          {/* Hooks */}
          {allHooks.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Hooks</h5>
              <div className="space-y-3">
                {allHooks.map((hookSet, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10">
                    <h6 className="text-xs font-bold text-white mb-2">{hookSet.ad_set_name ?? `Ad Set ${i + 1}`}</h6>
                    <div className="space-y-1.5">
                      {hookSet.hooks?.map((h, j) => (
                        <div key={j} className="flex items-start justify-between gap-2">
                          <span className="text-xs text-brand-silver/80 flex-1">&ldquo;{h.hook_text}&rdquo;</span>
                          {h.scroll_stop_power != null && (
                            <span className="text-[10px] font-bold text-brand-electric whitespace-nowrap">
                              {h.scroll_stop_power}/100
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Primary Copy */}
          {allCopy.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Primary Copy</h5>
              <div className="space-y-3">
                {allCopy.map((copySet, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10">
                    <h6 className="text-xs font-bold text-white mb-2">{copySet.ad_set_name ?? `Ad Set ${i + 1}`}</h6>
                    <div className="space-y-2">
                      {copySet.variants?.map((v, j) => (
                        <div key={j} className="space-y-1 border-l-2 border-brand-electric/20 pl-2">
                          <span className="text-[10px] font-medium text-brand-electric">{v.variant_id}</span>
                          {v.short?.text && (
                            <div className="text-xs text-brand-silver/70">
                              <span className="text-[10px] text-brand-silver/40 mr-1">Short:</span>
                              {v.short.text}
                            </div>
                          )}
                          {v.medium?.text && (
                            <div className="text-xs text-brand-silver/70">
                              <span className="text-[10px] text-brand-silver/40 mr-1">Medium:</span>
                              {v.medium.text}
                            </div>
                          )}
                          {v.long?.text && (
                            <div className="text-xs text-brand-silver/70">
                              <span className="text-[10px] text-brand-silver/40 mr-1">Long:</span>
                              <span className="line-clamp-3">{v.long.text}</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* CTAs */}
          {allCtas.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">CTAs</h5>
              <div className="space-y-3">
                {allCtas.map((ctaSet, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10">
                    <h6 className="text-xs font-bold text-white mb-2">{ctaSet.ad_set_name ?? `Ad Set ${i + 1}`}</h6>
                    <div className="space-y-1.5">
                      {ctaSet.cta_variants?.map((c, j) => (
                        <div key={j} className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="bg-brand-electric/20 text-brand-electric text-[10px] font-bold px-1.5 py-0.5 rounded">
                              {c.cta_button}
                            </span>
                            <span className="text-xs text-brand-silver/80">{c.cta_text}</span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] text-brand-silver/40">
                            {c.urgency_score != null && <span>Urgency: {c.urgency_score}</span>}
                            {c.clarity_score != null && <span>Clarity: {c.clarity_score}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Compliance Tab */}
      {activeTab === 'compliance' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-xs font-medium text-brand-silver/60">Overall Pass Rate:</span>
            <span className={`text-sm font-bold ${passRate >= 0.9 ? 'text-emerald-400' : passRate >= 0.7 ? 'text-amber-400' : 'text-red-400'}`}>
              {(passRate * 100).toFixed(0)}%
            </span>
          </div>
          {allCompliance.length === 0 ? (
            <p className="text-xs text-brand-silver/50">No compliance results available.</p>
          ) : (
            <div className="space-y-2">
              {allCompliance.map((c, i) => (
                <div
                  key={i}
                  className={`rounded-lg p-3 border ${
                    c.status === 'pass'
                      ? 'bg-emerald-500/5 border-emerald-500/20'
                      : c.status === 'warning'
                      ? 'bg-amber-500/5 border-amber-500/20'
                      : 'bg-red-500/5 border-red-500/20'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-white">{c.ad_set_name} — {c.copy_type}</span>
                    <span className={`text-[10px] font-bold uppercase ${
                      c.status === 'pass' ? 'text-emerald-400' : c.status === 'warning' ? 'text-amber-400' : 'text-red-400'
                    }`}>
                      {c.status}
                    </span>
                  </div>
                  {c.copy_text && (
                    <p className="text-[10px] text-brand-silver/50 line-clamp-1 mb-1">&ldquo;{c.copy_text}&rdquo;</p>
                  )}
                  {c.violations && c.violations.length > 0 && (
                    <div className="space-y-1 mt-1">
                      {c.violations.map((v, j) => (
                        <div key={j} className="text-[10px] text-brand-silver/60">
                          <span className="font-medium text-red-400">{v.rule}</span>: {v.description}
                          {v.suggested_fix && <span className="text-emerald-400 ml-1">Fix: {v.suggested_fix}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Ad Units Tab */}
      {activeTab === 'units' && (
        <div className="space-y-4">
          {allUnits.length === 0 ? (
            <p className="text-xs text-brand-silver/50">No assembled ad units.</p>
          ) : (
            <div className="space-y-3">
              {allUnits.map((unit, i) => (
                <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/10 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-white">{unit.ad_set_name}</span>
                      <span className="text-[10px] text-brand-silver/40">{unit.unit_id}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {unit.ad_format && (
                        <span className="bg-violet-500/20 text-violet-400 text-[10px] px-1.5 py-0.5 rounded">
                          {unit.ad_format}
                        </span>
                      )}
                      {unit.image_copy_coherence != null && (
                        <span className={`text-[10px] font-bold ${
                          unit.image_copy_coherence >= 80 ? 'text-emerald-400' : unit.image_copy_coherence >= 60 ? 'text-amber-400' : 'text-red-400'
                        }`}>
                          Coherence: {unit.image_copy_coherence}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div className="space-y-1">
                      {unit.headline && (
                        <div>
                          <span className="text-[10px] text-brand-silver/40">Headline:</span>
                          <p className="text-xs text-white font-medium">{unit.headline}</p>
                        </div>
                      )}
                      {unit.primary_text && (
                        <div>
                          <span className="text-[10px] text-brand-silver/40">Body ({unit.copy_length}):</span>
                          <p className="text-xs text-brand-silver/70 line-clamp-3">{unit.primary_text}</p>
                        </div>
                      )}
                    </div>
                    <div className="space-y-1">
                      {unit.cta_button && (
                        <div className="flex items-center gap-1">
                          <span className="text-[10px] text-brand-silver/40">CTA:</span>
                          <span className="bg-brand-electric/20 text-brand-electric text-[10px] font-bold px-1.5 py-0.5 rounded">
                            {unit.cta_button}
                          </span>
                          {unit.cta_text && <span className="text-xs text-brand-silver/60">{unit.cta_text}</span>}
                        </div>
                      )}
                      {unit.image_variant_id && (
                        <div className="text-[10px] text-brand-silver/40">
                          Image: {unit.image_variant_id} ({unit.image_aspect_ratio}) — {unit.target_placement}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function CampaignArchitectureSection({
  blueprint,
  funnelMap,
  targetingSpecs,
  placementBudget,
  testPlan,
  kpiTargets,
  performanceProjections,
  riskAssessment,
  creativeBriefs,
  specialAdCategory,
  confidenceScore,
  findings,
  recommendations,
}: {
  blueprint?: CAABlueprint;
  funnelMap?: CAAFunnelMap;
  targetingSpecs?: CAATargetingSpec[];
  placementBudget?: Record<string, unknown>;
  testPlan?: CAATestPlan;
  kpiTargets?: Record<string, Record<string, number>>;
  performanceProjections?: CAAPerformanceProjections;
  riskAssessment?: CAARiskAssessment;
  creativeBriefs?: CAACreativeBrief[];
  specialAdCategory?: string;
  confidenceScore?: number;
  findings?: string[];
  recommendations?: string[];
}) {
  const [activeTab, setActiveTab] = useState<'overview' | 'funnel' | 'targeting' | 'structure' | 'tests' | 'projections'>('overview');

  const tabs = [
    { key: 'overview' as const, label: 'Overview' },
    { key: 'funnel' as const, label: 'Funnel Map' },
    { key: 'targeting' as const, label: 'Audience Targeting' },
    { key: 'structure' as const, label: 'Campaign Structure' },
    { key: 'tests' as const, label: 'A/B Test Plan' },
    { key: 'projections' as const, label: 'Projections & KPIs' },
  ];

  const adSets = blueprint?.ad_sets ?? [];
  const stages = funnelMap?.stages ?? [];
  const specs = targetingSpecs ?? [];
  const tests = testPlan?.tests ?? [];
  const risks = riskAssessment?.risks ?? [];
  const briefs = creativeBriefs ?? [];

  function scoreBg(score: number) {
    if (score >= 80) return 'bg-green-400';
    if (score >= 60) return 'bg-amber-400';
    return 'bg-red-400';
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-bold text-white">Campaign Architecture Blueprint</h3>
        {confidenceScore != null && (() => {
          const pct = confidenceScore <= 1 ? Math.round(confidenceScore * 100) : Math.round(confidenceScore);
          return (
            <div className="flex items-center gap-2">
              <div className="w-24 h-2 rounded-full bg-white/10">
                <div className={`h-2 rounded-full ${scoreBg(pct)}`} style={{ width: `${pct}%` }} />
              </div>
              <span className="text-xs text-brand-silver">{pct}%</span>
            </div>
          );
        })()}
        {specialAdCategory && specialAdCategory !== 'NONE' && (
          <span className="px-2 py-1 text-xs rounded bg-amber-900/40 text-amber-300 border border-amber-700/50">
            Special Ad Category: {specialAdCategory}
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 overflow-x-auto pb-1 border-b border-white/10">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-3 py-1.5 text-xs font-medium rounded-t whitespace-nowrap transition-colors ${
              activeTab === t.key
                ? 'bg-white/10 text-white border-b-2 border-brand-electric'
                : 'text-brand-silver/60 hover:text-brand-silver'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-4">
          {blueprint && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {blueprint.campaign_name && (
                <div className="p-3 rounded-lg bg-white/5">
                  <div className="text-xs text-brand-silver/60 mb-1">Campaign</div>
                  <div className="text-sm text-white font-medium break-all">{blueprint.campaign_name}</div>
                </div>
              )}
              {blueprint.campaign_objective && (
                <div className="p-3 rounded-lg bg-white/5">
                  <div className="text-xs text-brand-silver/60 mb-1">Objective</div>
                  <div className="text-sm text-white font-medium">{blueprint.campaign_objective}</div>
                </div>
              )}
              {blueprint.daily_budget != null && (
                <div className="p-3 rounded-lg bg-white/5">
                  <div className="text-xs text-brand-silver/60 mb-1">Daily Budget</div>
                  <div className="text-sm text-white font-medium">${blueprint.daily_budget.toLocaleString()}</div>
                </div>
              )}
              {blueprint.bid_strategy && (
                <div className="p-3 rounded-lg bg-white/5">
                  <div className="text-xs text-brand-silver/60 mb-1">Bid Strategy</div>
                  <div className="text-sm text-white font-medium">{blueprint.bid_strategy}</div>
                </div>
              )}
            </div>
          )}
          {/* Quick stats */}
          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 rounded-lg bg-white/5 text-center">
              <div className="text-2xl font-bold text-brand-electric">{adSets.length}</div>
              <div className="text-xs text-brand-silver/60">Ad Sets</div>
            </div>
            <div className="p-3 rounded-lg bg-white/5 text-center">
              <div className="text-2xl font-bold text-brand-electric">{stages.length}</div>
              <div className="text-xs text-brand-silver/60">Funnel Stages</div>
            </div>
            <div className="p-3 rounded-lg bg-white/5 text-center">
              <div className="text-2xl font-bold text-brand-electric">{tests.length}</div>
              <div className="text-xs text-brand-silver/60">A/B Tests</div>
            </div>
          </div>
          {/* Risk Assessment */}
          {risks.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">Risk Assessment</h4>
              {risks.map((r, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-white/5">
                  <span className={`px-1.5 py-0.5 text-[10px] rounded ${
                    r.severity === 'high' ? 'bg-red-900/40 text-red-300' :
                    r.severity === 'medium' ? 'bg-amber-900/40 text-amber-300' :
                    'bg-green-900/40 text-green-300'
                  }`}>{r.severity}</span>
                  <div>
                    <div className="text-xs text-white">{r.description}</div>
                    {r.mitigation && <div className="text-xs text-brand-silver/60 mt-0.5">Mitigation: {r.mitigation}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Funnel Map Tab */}
      {activeTab === 'funnel' && (
        <div className="space-y-4">
          {stages.length > 0 ? (
            <>
              {/* Budget allocation bar */}
              <div className="flex rounded-lg overflow-hidden h-8">
                {stages.map((s, i) => {
                  const colors = ['bg-blue-500', 'bg-purple-500', 'bg-green-500', 'bg-amber-500'];
                  return (
                    <div
                      key={i}
                      className={`${colors[i % colors.length]} flex items-center justify-center text-[10px] text-white font-medium`}
                      style={{ width: `${s.budget_pct ?? 0}%` }}
                      title={`${s.stage?.toUpperCase()}: ${s.budget_pct}%`}
                    >
                      {(s.budget_pct ?? 0) >= 10 ? `${s.stage?.toUpperCase()} ${s.budget_pct}%` : ''}
                    </div>
                  );
                })}
              </div>
              {/* Stage table */}
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-brand-silver/60 border-b border-white/10">
                    <th className="text-left py-2 px-2">Stage</th>
                    <th className="text-left py-2 px-2">Meta Objective</th>
                    <th className="text-right py-2 px-2">Budget %</th>
                    <th className="text-left py-2 px-2">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {stages.map((s, i) => (
                    <tr key={i} className="border-b border-white/5">
                      <td className="py-2 px-2 text-white font-medium">{s.stage?.toUpperCase()}</td>
                      <td className="py-2 px-2 text-brand-electric">{s.meta_objective}</td>
                      <td className="py-2 px-2 text-right text-white">{s.budget_pct}%</td>
                      <td className="py-2 px-2 text-brand-silver/80">{s.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p className="text-sm text-brand-silver/60">No funnel map data available.</p>
          )}
        </div>
      )}

      {/* Audience Targeting Tab */}
      {activeTab === 'targeting' && (
        <div className="space-y-4">
          {specs.length > 0 ? specs.map((spec, i) => (
            <div key={i} className="p-4 rounded-lg bg-white/5 space-y-2">
              <div className="flex items-center justify-between">
                <h5 className="text-sm font-medium text-white">{spec.ad_set_name || `Ad Set ${i + 1}`}</h5>
                <span className="text-xs text-brand-silver/60">{spec.funnel_stage?.toUpperCase()}</span>
              </div>
              {spec.demographics && Object.keys(spec.demographics).length > 0 && (
                <div className="text-xs text-brand-silver/80">
                  Demographics: {Object.entries(spec.demographics).map(([k, v]) => `${k}: ${v}`).join(', ')}
                </div>
              )}
              {spec.interests && spec.interests.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {spec.interests.map((int, j) => (
                    <span key={j} className="px-2 py-0.5 text-[10px] rounded-full bg-blue-900/30 text-blue-300">{int}</span>
                  ))}
                </div>
              )}
              {spec.behaviors && spec.behaviors.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {spec.behaviors.map((b, j) => (
                    <span key={j} className="px-2 py-0.5 text-[10px] rounded-full bg-purple-900/30 text-purple-300">{b}</span>
                  ))}
                </div>
              )}
              {spec.custom_audiences && spec.custom_audiences.length > 0 && (
                <div className="text-xs text-brand-silver/80">Custom audiences: {spec.custom_audiences.join(', ')}</div>
              )}
              {spec.estimated_audience_size != null && spec.estimated_audience_size > 0 && (
                <div className="text-xs text-brand-silver/60">Est. audience: {spec.estimated_audience_size.toLocaleString()}</div>
              )}
            </div>
          )) : (
            <p className="text-sm text-brand-silver/60">No targeting specs available.</p>
          )}
        </div>
      )}

      {/* Campaign Structure Tab */}
      {activeTab === 'structure' && (
        <div className="space-y-3">
          {blueprint?.campaign_name && (
            <div className="p-3 rounded-lg bg-white/5 border border-white/10">
              <div className="text-sm font-medium text-brand-electric mb-2">
                Campaign: {blueprint.campaign_name}
              </div>
              <div className="text-xs text-brand-silver/60 space-x-4">
                {blueprint.cbo_enabled != null && <span>CBO: {blueprint.cbo_enabled ? 'Enabled' : 'Disabled'}</span>}
                {blueprint.buying_type && <span>Buying: {blueprint.buying_type}</span>}
              </div>
            </div>
          )}
          {adSets.map((as_, i) => (
            <div key={i} className="ml-4 p-3 rounded-lg bg-white/5 border-l-2 border-brand-electric/30">
              <div className="flex items-center justify-between mb-2">
                <h5 className="text-sm font-medium text-white">{as_.name || `Ad Set ${i + 1}`}</h5>
                <div className="flex gap-2 text-xs">
                  {as_.funnel_stage && <span className="text-brand-silver/60">{as_.funnel_stage.toUpperCase()}</span>}
                  {as_.daily_budget != null && <span className="text-green-400">${as_.daily_budget}/day</span>}
                </div>
              </div>
              {as_.objective && <div className="text-xs text-brand-silver/80 mb-1">Objective: {as_.objective}</div>}
              {as_.placements && as_.placements.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-1">
                  {as_.placements.map((p, j) => (
                    <span key={j} className="px-1.5 py-0.5 text-[10px] rounded bg-white/10 text-brand-silver">{p}</span>
                  ))}
                </div>
              )}
              {as_.optimization_goal && <div className="text-xs text-brand-silver/60">Optimize for: {as_.optimization_goal}</div>}
            </div>
          ))}
          {adSets.length === 0 && (
            <p className="text-sm text-brand-silver/60">No campaign structure available.</p>
          )}
        </div>
      )}

      {/* A/B Test Plan Tab */}
      {activeTab === 'tests' && (
        <div className="space-y-4">
          {testPlan?.total_testing_budget_pct != null && (
            <div className="p-3 rounded-lg bg-white/5 flex items-center justify-between">
              <span className="text-xs text-brand-silver/60">Total testing budget</span>
              <span className="text-sm text-white font-medium">{testPlan.total_testing_budget_pct}%</span>
            </div>
          )}
          {tests.length > 0 ? tests.map((t, i) => (
            <div key={i} className="p-4 rounded-lg bg-white/5 space-y-2">
              <div className="flex items-center justify-between">
                <h5 className="text-sm font-medium text-white">{t.variable}</h5>
                {t.priority && (
                  <span className={`px-2 py-0.5 text-[10px] rounded ${
                    t.priority === 'high' ? 'bg-red-900/30 text-red-300' :
                    t.priority === 'medium' ? 'bg-amber-900/30 text-amber-300' :
                    'bg-green-900/30 text-green-300'
                  }`}>{t.priority}</span>
                )}
              </div>
              {t.variants && t.variants.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {t.variants.map((v, j) => (
                    <span key={j} className="px-2 py-0.5 text-[10px] rounded bg-white/10 text-brand-silver">{v}</span>
                  ))}
                </div>
              )}
              <div className="text-xs text-brand-silver/60 space-x-3">
                {t.duration_days && <span>{t.duration_days} days</span>}
                {t.sample_size_per_variant && <span>{t.sample_size_per_variant.toLocaleString()} samples/variant</span>}
                {t.success_metric && <span>Metric: {t.success_metric}</span>}
              </div>
            </div>
          )) : (
            <p className="text-sm text-brand-silver/60">No A/B test plan available.</p>
          )}
        </div>
      )}

      {/* Projections & KPIs Tab */}
      {activeTab === 'projections' && (
        <div className="space-y-4">
          {/* Performance projections */}
          {performanceProjections && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {performanceProjections.estimated_reach != null && (
                <div className="p-3 rounded-lg bg-white/5 text-center">
                  <div className="text-lg font-bold text-white">{performanceProjections.estimated_reach.toLocaleString()}</div>
                  <div className="text-[10px] text-brand-silver/60">Est. Reach</div>
                </div>
              )}
              {performanceProjections.estimated_impressions != null && (
                <div className="p-3 rounded-lg bg-white/5 text-center">
                  <div className="text-lg font-bold text-white">{performanceProjections.estimated_impressions.toLocaleString()}</div>
                  <div className="text-[10px] text-brand-silver/60">Est. Impressions</div>
                </div>
              )}
              {performanceProjections.estimated_clicks != null && (
                <div className="p-3 rounded-lg bg-white/5 text-center">
                  <div className="text-lg font-bold text-white">{performanceProjections.estimated_clicks.toLocaleString()}</div>
                  <div className="text-[10px] text-brand-silver/60">Est. Clicks</div>
                </div>
              )}
              {performanceProjections.estimated_conversions != null && (
                <div className="p-3 rounded-lg bg-white/5 text-center">
                  <div className="text-lg font-bold text-white">{performanceProjections.estimated_conversions.toLocaleString()}</div>
                  <div className="text-[10px] text-brand-silver/60">Est. Conversions</div>
                </div>
              )}
              {performanceProjections.projected_roas != null && (
                <div className="p-3 rounded-lg bg-white/5 text-center">
                  <div className="text-lg font-bold text-brand-electric">{performanceProjections.projected_roas.toFixed(1)}x</div>
                  <div className="text-[10px] text-brand-silver/60">Projected ROAS</div>
                </div>
              )}
            </div>
          )}
          {/* KPI targets table */}
          {kpiTargets && Object.keys(kpiTargets).length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">KPI Targets per Funnel</h4>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-brand-silver/60 border-b border-white/10">
                    <th className="text-left py-2 px-2">Stage</th>
                    <th className="text-right py-2 px-2">CPM</th>
                    <th className="text-right py-2 px-2">CTR</th>
                    <th className="text-right py-2 px-2">CPC</th>
                    <th className="text-right py-2 px-2">CPA</th>
                    <th className="text-right py-2 px-2">ROAS</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(kpiTargets).map(([stage, kpis]) => (
                    <tr key={stage} className="border-b border-white/5">
                      <td className="py-2 px-2 text-white font-medium">{stage.toUpperCase()}</td>
                      <td className="py-2 px-2 text-right text-brand-silver">{kpis.cpm != null ? `$${kpis.cpm.toFixed(2)}` : '—'}</td>
                      <td className="py-2 px-2 text-right text-brand-silver">{kpis.ctr != null ? `${kpis.ctr.toFixed(2)}%` : '—'}</td>
                      <td className="py-2 px-2 text-right text-brand-silver">{kpis.cpc != null ? `$${kpis.cpc.toFixed(2)}` : '—'}</td>
                      <td className="py-2 px-2 text-right text-brand-silver">{kpis.cpa != null ? `$${kpis.cpa.toFixed(2)}` : '—'}</td>
                      <td className="py-2 px-2 text-right text-brand-electric">{kpis.roas != null ? `${kpis.roas.toFixed(1)}x` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {/* Creative briefs */}
          {briefs.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Creative Briefs</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {briefs.map((b, i) => (
                  <div key={i} className="p-3 rounded-lg bg-white/5 space-y-1">
                    <div className="text-sm font-medium text-white">{b.ad_set_name}</div>
                    {b.format && <div className="text-xs text-brand-electric">{b.format}</div>}
                    {b.headline && <div className="text-xs text-white">{b.headline}</div>}
                    {b.primary_text && <div className="text-xs text-brand-silver/80">{b.primary_text}</div>}
                    {b.cta && <div className="text-xs text-brand-silver/60">CTA: {b.cta}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Findings & Recommendations */}
      {findings && findings.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Findings</h4>
          {findings.map((f, i) => (
            <div key={i} className="mb-1"><MarkdownMessage content={f} /></div>
          ))}
        </section>
      )}
      {recommendations && recommendations.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">Recommendations</h4>
          {recommendations.map((r, i) => (
            <div key={i} className="mb-1"><MarkdownMessage content={r} /></div>
          ))}
        </section>
      )}
    </div>
  );
}

// ── Campaign Structure — collapsible hierarchy for published ad campaigns ──

function CampaignStructure({
  pubCampaign,
  adSets,
  adCount,
}: {
  pubCampaign: Record<string, unknown>;
  adSets: Array<Record<string, unknown>>;
  adCount: number;
}) {
  const [expandedAdSet, setExpandedAdSet] = useState<string | null>(null);
  const [showCampaignId, setShowCampaignId] = useState(false);

  const pubAdSets = (pubCampaign.ad_sets ?? []) as Array<Record<string, unknown>>;
  const pubAds = (pubCampaign.ads ?? []) as Array<Record<string, unknown>>;
  const adsPerAdSet = pubAdSets.length > 0 ? Math.ceil(pubAds.length / pubAdSets.length) : pubAds.length;

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">
        Campaign Structure
      </h4>

      {/* Campaign row */}
      <div className="rounded-lg border border-brand-silver/20 bg-white/[0.03] overflow-hidden">
        <button
          onClick={() => setShowCampaignId(!showCampaignId)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-white/[0.03] transition-colors text-left"
        >
          <Megaphone className="w-4 h-4 text-brand-electric shrink-0" />
          <span className="text-xs font-medium text-brand-silver flex-1 truncate">
            {(pubCampaign.campaign_name as string) ?? 'Campaign'}
          </span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
            (pubCampaign.campaign_status as string) === 'ACTIVE'
              ? 'bg-emerald-500/15 text-emerald-400'
              : 'bg-amber-500/15 text-amber-400'
          }`}>
            {pubCampaign.campaign_status as string}
          </span>
          {showCampaignId ? (
            <ChevronDown className="w-3.5 h-3.5 text-brand-silver/40 shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-brand-silver/40 shrink-0" />
          )}
        </button>
        {showCampaignId && (
          <div className="px-3 pb-2.5 pt-0">
            <code className="text-[10px] text-brand-silver/50 bg-white/[0.03] px-2 py-0.5 rounded block truncate">
              ID: {pubCampaign.campaign_id as string}
            </code>
          </div>
        )}
      </div>

      {/* Ad Sets — each expandable to show its details */}
      <div className="space-y-1.5 ml-4 border-l border-brand-silver/10 pl-3">
        {adSets.map((adSet, i) => {
          const adSetKey = `adset-${i}`;
          const isExpanded = expandedAdSet === adSetKey;
          const adSetName = (adSet.ad_set_name as string) ?? `Ad Set ${i + 1}`;
          const persona = adSet.persona as string | undefined;
          const funnelStage = adSet.funnel_stage as string | undefined;
          const dailyBudget = adSet.daily_budget_usd as number | undefined;
          const targetingSummary = adSet.targeting_summary as string | undefined;
          const creatives = (adSet.creatives ?? []) as Array<Record<string, unknown>>;
          const pubAdSetId = pubAdSets[i]?.ad_set_id as string | undefined;

          return (
            <div key={adSetKey} className="rounded-lg border border-brand-silver/10 bg-white/[0.02] overflow-hidden">
              <button
                onClick={() => setExpandedAdSet(isExpanded ? null : adSetKey)}
                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-white/[0.03] transition-colors text-left"
              >
                <Target className="w-3.5 h-3.5 text-amber-400/70 shrink-0" />
                <span className="text-[11px] font-medium text-brand-silver flex-1 truncate">
                  {adSetName}
                </span>
                {funnelStage && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-brand-electric/10 text-brand-electric/70 shrink-0">
                    {funnelStage}
                  </span>
                )}
                <span className="text-[10px] text-brand-silver/40 shrink-0">
                  {creatives.length > 0 ? `${creatives.length} ads` : `~${adsPerAdSet} ads`}
                </span>
                {isExpanded ? (
                  <ChevronDown className="w-3 h-3 text-brand-silver/40 shrink-0" />
                ) : (
                  <ChevronRight className="w-3 h-3 text-brand-silver/40 shrink-0" />
                )}
              </button>

              {isExpanded && (
                <div className="px-3 pb-2.5 space-y-2 border-t border-brand-silver/5">
                  {/* Persona + targeting */}
                  {persona && (
                    <div className="flex items-center gap-1.5 mt-2">
                      <Users className="w-3 h-3 text-brand-silver/40" />
                      <span className="text-[10px] text-brand-silver/60">
                        {persona}
                      </span>
                    </div>
                  )}
                  {targetingSummary && (
                    <p className="text-[10px] text-brand-silver/50 leading-relaxed">
                      {targetingSummary}
                    </p>
                  )}
                  {/* Budget */}
                  {dailyBudget != null && (
                    <div className="flex items-center gap-1.5">
                      <DollarSign className="w-3 h-3 text-brand-silver/40" />
                      <span className="text-[10px] text-brand-silver/60">
                        ${dailyBudget.toFixed(2)}/day
                      </span>
                    </div>
                  )}
                  {/* Creatives */}
                  {creatives.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] text-brand-silver/40 font-medium">Creatives:</span>
                      {creatives.map((creative, ci) => (
                        <div key={ci} className="flex items-center gap-1.5 ml-2">
                          <Layers className="w-2.5 h-2.5 text-brand-silver/30" />
                          <span className="text-[10px] text-brand-silver/50 truncate">
                            {(creative.headline as string) ?? (creative.primary_text as string)?.slice(0, 60) ?? `Creative ${ci + 1}`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Meta Ad Set ID */}
                  {pubAdSetId && (
                    <code className="text-[9px] text-brand-silver/40 bg-white/[0.03] px-1.5 py-0.5 rounded block truncate mt-1">
                      ID: {pubAdSetId}
                    </code>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Summary footer */}
      <div className="flex items-center gap-4 pt-1 text-[10px] text-brand-silver/40">
        <span>{adSets.length} ad sets</span>
        <span>{adCount} ads</span>
        <span>{((pubCampaign.creative_ids ?? []) as Array<unknown>).length} creatives</span>
      </div>
    </div>
  );
}

export default function ResultDashboard({
  resultData,
  manifestName,
  jobId,
  chatSessionId,
  jobStatus,
  onApprovalComplete,
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
  // Check top-level (promoted by ManagerNode) first, then node_payloads fallback
  const mraNodePayloads = (resultData.node_payloads as Record<string, Record<string, unknown>> | undefined) ??
    (resultData.node_results as Record<string, Record<string, unknown>> | undefined);
  const mraPayload = mraNodePayloads?.market_research;
  const hasMarketResearch =
    resultData.market_sizing != null || resultData.market_overview != null ||
    mraPayload?.market_sizing != null || mraPayload?.market_overview != null;

  // ── Detect competitor intelligence data ────────────────────────
  const hasCompetitorIntelligence =
    resultData.competitors != null ||
    resultData.competitor_matrix != null ||
    resultData.swot_analyses != null;

  // ── Detect audience persona data ─────────────────────────────
  const hasAudiencePersona =
    resultData.personas != null || resultData.journey_maps != null;

  // ── Detect trend/cultural insights data ────────────────────────
  const hasTrendCultural =
    resultData.scored_trends != null ||
    resultData.trend_report != null ||
    resultData.trend_persona_matrix != null;

  // ── Detect brand positioning data ──────────────────────────────
  const hasBrandPositioning =
    resultData.recommended_positioning != null ||
    resultData.positioning_candidates != null ||
    resultData.perceptual_maps != null;

  // ── Detect brand architecture data ───────────────────────────
  const hasBrandArchitecture =
    resultData.recommendation != null &&
    typeof resultData.recommendation === 'object' &&
    (resultData.recommendation as Record<string, unknown>).recommended_model != null &&
    resultData.hierarchy != null;

  // ── Detect brand personality data ───────────────────────────────
  const hasBrandPersonality =
    resultData.aaker_profile != null ||
    resultData.archetype != null ||
    resultData.values_hierarchy != null;

  // ── Detect brand naming data ──────────────────────────────────
  const hasBrandNaming =
    resultData.name_candidates != null ||
    resultData.naming_brief != null;

  // ── Detect brand story data ──────────────────────────────────
  const hasBrandStory =
    resultData.origin_story != null ||
    resultData.narrative_package != null ||
    resultData.mission_vision != null;

  // ── Detect voice of customer data ───────────────────────────────
  const hasVoiceOfCustomer =
    resultData.voc_health_score != null ||
    resultData.sentiment != null ||
    resultData.themes != null ||
    resultData.nps_analysis != null ||
    resultData.pain_point_priority_matrix != null;

  // ── Detect brand discovery (2+ WF1 agents present → show tabbed) ──
  const wf1AgentCount = [hasMarketResearch, hasCompetitorIntelligence, hasAudiencePersona, hasTrendCultural, hasVoiceOfCustomer].filter(Boolean).length;
  const hasBrandDiscovery = wf1AgentCount >= 2;

  // ── Per-node payloads ───────────────────────────────────────────
  // Orchestrator namespaces flat agent responses under
  // result_data.node_payloads.<node_id> to prevent overwrites across
  // WF3 pipelines. Fall back to legacy node_results, then top-level.
  const nodePayloads =
    (resultData.node_payloads as Record<string, Record<string, unknown>> | undefined) ??
    (resultData.node_results as Record<string, Record<string, unknown>> | undefined);
  const caaNodeData = nodePayloads?.campaign_architecture;

  // ── Detect campaign architecture data ───────────────────────────
  const hasCampaignArchitecture =
    caaNodeData?.blueprint != null ||
    caaNodeData?.funnel_map != null ||
    caaNodeData?.targeting_specs != null ||
    resultData.blueprint != null ||
    resultData.funnel_map != null ||
    resultData.targeting_specs != null;

  // ── Detect creative generation data ───────────────────────────
  const cgaNodeData = nodePayloads?.creative_generation;
  const hasCreativeGeneration =
    cgaNodeData?.creative_package != null ||
    cgaNodeData?.ad_units != null ||
    cgaNodeData?.copy_variants != null ||
    cgaNodeData?.generated_images != null ||
    resultData.creative_package != null ||
    resultData.ad_units != null;

  // ── Detect ad-publishing / approval data ────────────────────────
  const adPubNodeData = nodePayloads?.ad_publishing;
  const adPubData = adPubNodeData ?? resultData;
  const publishResult = (resultData.publish_result ?? adPubData?.publish_result) as Record<string, unknown> | undefined;
  const hasAdPublishing =
    adPubData?.approval_request_id != null ||
    adPubData?.preview_data != null ||
    publishResult != null;

  // ── Extract well-known keys ──────────────────────────────────────
  const summary = resultData.summary as string | undefined;
  const findings = resultData.findings as string[] | undefined;
  const recommendations = resultData.recommendations as string[] | undefined;
  const score = resultData.score as number | undefined;

  // ── Route to approval panel for ad-publishing awaiting_approval ──
  const approvalRequestId = (adPubData?.approval_request_id ?? resultData.approval_request_id) as string | undefined;
  // Only treat the job as awaiting approval when the live job status
  // says so. The persisted node_payloads still carry the original
  // gate output (status=awaiting_approval) even after the user
  // approves, so relying on them would keep the approval panel up
  // forever once the job flips to completed/failed.
  const isAwaitingApproval = jobStatus === 'awaiting_approval';
  if (hasAdPublishing && approvalRequestId && isAwaitingApproval && jobId) {
    const previewData = (adPubData?.preview_data ?? resultData.preview_data ?? {}) as Record<string, unknown>;
    const sandboxMode = (adPubData?.sandbox_mode ?? resultData.sandbox_mode ?? true) as boolean;
    const planWarnings = (adPubData?.plan_warnings ?? resultData.plan_warnings ?? []) as string[];
    return (
      <div className="glass-card p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-heading font-semibold text-white">
            Campaign Approval
          </h3>
        </div>
        {findings && findings.length > 0 && (
          <section>
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
              Key Findings
            </h4>
            <ul className="space-y-1">
              {findings.map((f, i) => (
                <li key={i} className="text-xs text-brand-silver/70 flex items-start gap-2">
                  <span className="text-brand-electric mt-0.5">&#8226;</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {/* Upstream WF3 agents (CAA + CGA) — surfaced above the
            approval panel so reviewers can inspect every agent's
            output, not just the final ad-publishing payload. */}
        {hasCampaignArchitecture && (
          <CampaignArchitectureSection
            blueprint={(caaNodeData?.blueprint ?? resultData.blueprint) as CAABlueprint | undefined}
            funnelMap={(caaNodeData?.funnel_map ?? resultData.funnel_map) as CAAFunnelMap | undefined}
            targetingSpecs={(caaNodeData?.targeting_specs ?? resultData.targeting_specs) as CAATargetingSpec[] | undefined}
            placementBudget={(caaNodeData?.placement_budget ?? resultData.placement_budget) as Record<string, unknown> | undefined}
            testPlan={(caaNodeData?.test_plan ?? resultData.test_plan) as CAATestPlan | undefined}
            kpiTargets={(caaNodeData?.kpi_targets ?? resultData.kpi_targets) as Record<string, Record<string, number>> | undefined}
            performanceProjections={(caaNodeData?.performance_projections ?? resultData.performance_projections) as CAAPerformanceProjections | undefined}
            riskAssessment={(caaNodeData?.risk_assessment ?? resultData.risk_assessment) as CAARiskAssessment | undefined}
            creativeBriefs={(caaNodeData?.creative_briefs ?? resultData.creative_briefs) as CAACreativeBrief[] | undefined}
            specialAdCategory={(caaNodeData?.special_ad_category ?? resultData.special_ad_category) as string | undefined}
            confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.campaign_architecture ?? (caaNodeData?.confidence_score ?? resultData.confidence_score)) as number | undefined}
            findings={(caaNodeData?.findings as string[] | undefined) ?? findings}
            recommendations={(caaNodeData?.recommendations as string[] | undefined) ?? recommendations}
          />
        )}
        {hasCreativeGeneration && (
          <CreativeGenerationSection
            creativePackage={(cgaNodeData?.creative_package ?? resultData.creative_package) as CGACreativePackage | undefined}
            adSetPackages={(cgaNodeData?.ad_set_packages ?? resultData.ad_set_packages) as CGAAdSetPackage[] | undefined}
            adUnits={(cgaNodeData?.ad_units ?? resultData.ad_units) as CGACreativeUnit[] | undefined}
            generatedImages={(cgaNodeData?.generated_images ?? resultData.generated_images) as CGAGeneratedImage[] | undefined}
            hooks={(cgaNodeData?.hooks ?? resultData.hooks) as CGAHookVariant[] | undefined}
            copyVariants={(cgaNodeData?.copy_variants ?? resultData.copy_variants) as CGACopySet[] | undefined}
            ctas={(cgaNodeData?.ctas ?? resultData.ctas) as CGACTASet[] | undefined}
            complianceResults={(cgaNodeData?.compliance_results ?? resultData.compliance_results) as CGAComplianceResult[] | undefined}
            totalImagesGenerated={(cgaNodeData?.total_images_generated ?? resultData.total_images_generated) as number | undefined}
            imageGenCostUsd={(cgaNodeData?.image_gen_cost_usd ?? resultData.image_gen_cost_usd) as number | undefined}
            compliancePassRate={(cgaNodeData?.compliance_pass_rate ?? resultData.compliance_pass_rate) as number | undefined}
            creativeQualityScore={(cgaNodeData?.creative_quality_score ?? resultData.creative_quality_score) as number | undefined}
            confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.creative_generation ?? (cgaNodeData?.confidence_score ?? resultData.confidence_score)) as number | undefined}
            imageGenFailed={(cgaNodeData?.image_gen_failed ?? resultData.image_gen_failed) as boolean | undefined}
            findings={(cgaNodeData?.findings as string[] | undefined) ?? findings}
            recommendations={(cgaNodeData?.recommendations as string[] | undefined) ?? recommendations}
          />
        )}
        <ApprovalPanel
          jobId={jobId}
          approvalRequestId={approvalRequestId}
          previewData={previewData}
          sandboxMode={sandboxMode}
          planWarnings={planWarnings}
          onApprovalComplete={onApprovalComplete}
        />
        {recommendations && recommendations.length > 0 && (
          <section>
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
              Recommendations
            </h4>
            <ul className="space-y-1">
              {recommendations.map((r, i) => (
                <li key={i} className="text-xs text-brand-silver/70 flex items-start gap-2">
                  <span className="text-emerald-400 mt-0.5">&#8226;</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    );
  }

  // ── Completed ad-publishing: show published campaign summary ────
  if (hasAdPublishing && publishResult && jobStatus === 'completed') {
    const pubCampaign = publishResult.published_campaign as Record<string, unknown> | undefined;
    const pubStatus = (publishResult.status ?? 'published') as string;
    const isPublished = pubStatus === 'published' || pubStatus === 'partial';
    const dailySpend = publishResult.daily_spend_committed_usd as number | undefined;
    const audienceSize = publishResult.targeting_audience_size as number | undefined;
    const isSandbox = (publishResult.sandbox_mode ?? adPubData?.sandbox_mode ?? true) as boolean;
    const previewData = (adPubData?.preview_data ?? resultData.preview_data) as Record<string, unknown> | undefined;
    const adSets = (previewData?.ad_sets ?? pubCampaign?.ad_sets ?? []) as Array<Record<string, unknown>>;
    const adCount = ((pubCampaign?.ads ?? []) as Array<unknown>).length;
    const creativeCount = ((pubCampaign?.creative_ids ?? []) as Array<unknown>).length;

    return (
      <div className="glass-card p-6 space-y-6">
        {/* Status banner */}
        <div className={`flex items-center gap-3 p-4 rounded-xl border ${
          isPublished
            ? 'border-emerald-500/30 bg-emerald-500/10'
            : 'border-amber-500/30 bg-amber-500/10'
        }`}>
          <CheckCircle2 className={`w-6 h-6 shrink-0 ${isPublished ? 'text-emerald-400' : 'text-amber-400'}`} />
          <div>
            <p className={`text-sm font-medium ${isPublished ? 'text-emerald-300' : 'text-amber-300'}`}>
              {isSandbox ? 'Campaign Published (Sandbox)' : 'Campaign Published & Live'}
            </p>
            <p className="text-xs text-brand-silver/50 mt-0.5">
              {isSandbox
                ? 'Campaign was published in sandbox mode — no real ads are running.'
                : 'Ads are now live on Meta. Monitor performance in Meta Ads Manager.'}
            </p>
          </div>
        </div>

        {/* Campaign overview */}
        <div>
          <h3 className="text-sm font-heading font-semibold text-white mb-3">
            {(pubCampaign?.campaign_name as string) ?? (previewData?.campaign_name as string) ?? 'Published Campaign'}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white/[0.03]">
              <Users className="w-4 h-4 text-brand-electric/60" />
              <div>
                <p className="text-[10px] text-brand-silver/40">Ad Sets</p>
                <p className="text-xs text-brand-silver font-medium">{adSets.length}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white/[0.03]">
              <Image className="w-4 h-4 text-brand-electric/60" />
              <div>
                <p className="text-[10px] text-brand-silver/40">Ads</p>
                <p className="text-xs text-brand-silver font-medium">{adCount}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white/[0.03]">
              <Image className="w-4 h-4 text-brand-electric/60" />
              <div>
                <p className="text-[10px] text-brand-silver/40">Creatives</p>
                <p className="text-xs text-brand-silver font-medium">{creativeCount}</p>
              </div>
            </div>
            {dailySpend != null && (
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white/[0.03]">
                <DollarSign className="w-4 h-4 text-brand-electric/60" />
                <div>
                  <p className="text-[10px] text-brand-silver/40">Daily Budget</p>
                  <p className="text-xs text-brand-silver font-medium">${dailySpend.toFixed(2)}</p>
                </div>
              </div>
            )}
          </div>
          {audienceSize != null && audienceSize > 0 && (
            <p className="text-[11px] text-brand-silver/40 mt-2">
              Estimated audience reach: {audienceSize.toLocaleString()}
            </p>
          )}
        </div>

        {/* Campaign Structure — hierarchical breakdown */}
        {pubCampaign && (
          <CampaignStructure
            pubCampaign={pubCampaign}
            adSets={adSets}
            adCount={adCount}
          />
        )}

        {/* Findings from the original execution */}
        {findings && findings.length > 0 && (
          <section>
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
              Key Findings
            </h4>
            <ul className="space-y-1">
              {findings.map((f, i) => (
                <li key={i} className="text-xs text-brand-silver/70 flex items-start gap-2">
                  <span className="text-brand-electric mt-0.5">&#8226;</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    );
  }

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
    // Trend & Cultural Insights keys
    'trend_report',
    'scored_trends',
    'trend_persona_matrix',
    'opportunity_alerts',
    'viral_patterns',
    'cultural_shifts',
    'generational_insights',
    'language_trends',
    'report_url',
    // Voice of Customer keys
    'voc_health_score',
    'voc_health_breakdown',
    'sentiment',
    'themes',
    'nps_analysis',
    'pain_point_priority_matrix',
    'strategy_bridge',
    'operating_mode',
    'data_coverage_score',
    'odoo_onboarding_recommendation',
    // Brand Architecture keys
    'recommendation',
    'hierarchy',
    'naming_hierarchy',
    'growth_path',
    'arch_strategy',
    'wf1_context_used',
    'bpa_context_used',
    'execution_time_ms',
    // Brand Positioning keys
    'recommended_positioning',
    'alternative_positions',
    'positioning_candidates',
    'canvas',
    'perceptual_maps',
    'differentiation',
    'strategy',
    'wf1_context_used',
    'confidence_scores',
    // Brand Personality keys
    'aaker_profile',
    'archetype',
    'values_hierarchy',
    'emotional_map',
    'voice_matrix',
    'character_brief',
    'baa_context_used',
    'sub_brand_constraint_applied',
    // Brand Naming & Tagline keys
    'name_candidates',
    'shortlisted_names',
    'taglines',
    'naming_brief',
    'availability_results',
    'scoring_summary',
    'bpv_context_used',
    // Brand Story & Narrative keys
    'origin_story',
    'mission_vision',
    'pitches',
    'channel_narratives',
    'story_style_guide',
    'subbrand_stories',
    'narrative_package',
    'wf2_strategy_summary',
    'nta_context_used',
    'gcs_uri',
    // Campaign Architecture keys
    'blueprint',
    'funnel_map',
    'targeting_specs',
    'placement_budget',
    'test_plan',
    'kpi_targets',
    'performance_projections',
    'risk_assessment',
    'creative_briefs',
    'special_ad_category',
    'meta_api_compatible',
    'wf2_context_used',
    'company_context_used',
    'tavily_benchmarks_used',
    'odoo_data_used',
    'rag_learnings_used',
    // Creative Generation keys
    'creative_package',
    'ad_set_packages',
    'ad_units',
    'generated_images',
    'hooks',
    'copy_variants',
    'ctas',
    'compliance_results',
    'creative_profiles',
    'total_images_generated',
    'total_images_refined',
    'image_gen_cost_usd',
    'compliance_pass_rate',
    'creative_quality_score',
    'image_gen_failed',
    'caa_context_used',
    'bsa_context_used',
    'baa_context_used',
    // Ad Publishing keys
    'approval_request_id',
    'preview_data',
    'sandbox_mode',
    'is_production',
    'plan_warnings',
    'preparation_time_ms',
    'publish_result',
    'status',
    // Orchestrator internals — already consumed above via nodePayloads
    'node_payloads',
    'node_results',
    'node_outputs',
    // Pipeline state keys — should never render as "Other sections"
    'tenant_context',
    'input_context',
    'input_prompt',
    'config',
    'previous_outputs',
    'global_config',
    'callback_url',
    'job_id',
    'tenant_id',
    'cancelled',
    'error',
    'error_message',
    'progress',
    'resolved_manifest_id',
    'brand_context_preamble',
    'brand_context_preamble_compact',
    // Noise from agent echoes
    'query',
    'sources',
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
          jobId={jobId}
          chatSessionId={chatSessionId}
        />
      </div>

      {/* Pipeline error banner */}
      {(resultData.error != null || resultData.error_message != null) && (() => {
        const msg = typeof resultData.error_message === 'string'
          ? resultData.error_message
          : typeof resultData.error === 'string'
            ? resultData.error
            : 'An error occurred during pipeline execution.';
        return (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
            <p className="text-sm font-medium text-red-400">{msg}</p>
          </div>
        );
      })()}

      {/* Score badge (only when meaningful, i.e. > 0, and not market research) */}
      {!hasBrandDiscovery && !hasMarketResearch && !hasCompetitorIntelligence && !hasAudiencePersona && !hasTrendCultural && !hasVoiceOfCustomer && !hasBrandArchitecture && !hasBrandPersonality && score !== undefined && score > 0 && (
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
      {summary && !hasBrandDiscovery && !hasMarketResearch && !hasCompetitorIntelligence && !hasAudiencePersona && !hasTrendCultural && !hasVoiceOfCustomer && !hasBrandPositioning && !hasBrandArchitecture && !hasBrandPersonality && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Summary
          </h4>
          <MarkdownMessage content={summary} />
        </section>
      )}

      {/* ── Brand Discovery (tabbed when 2+ WF1 agents present) ──── */}
      {hasBrandDiscovery && (
        <BrandDiscoverySection
          hasMarketResearch={hasMarketResearch}
          marketOverview={(resultData.market_overview ?? mraPayload?.market_overview) as string | undefined}
          marketSizing={(resultData.market_sizing ?? mraPayload?.market_sizing) as Record<string, unknown> | undefined}
          competitiveLandscape={(resultData.competitive_landscape ?? mraPayload?.competitive_landscape) as CompetitorEntry[] | undefined}
          industryTrends={(resultData.industry_trends ?? mraPayload?.industry_trends) as string[] | undefined}
          economicIndicators={(resultData.economic_indicators ?? mraPayload?.economic_indicators) as Record<string, unknown> | undefined}
          hasCompetitorIntelligence={hasCompetitorIntelligence}
          ciaExecutiveSummary={resultData.executive_summary as string | undefined}
          competitors={resultData.competitors as CIACompetitorProfile[] | undefined}
          competitorMatrix={resultData.competitor_matrix as Record<string, Record<string, number>> | undefined}
          swotAnalyses={resultData.swot_analyses as SWOTAnalysis[] | undefined}
          positioningGaps={resultData.positioning_gaps as PositioningGap[] | undefined}
          benchmarkingReport={resultData.benchmarking_report as Record<string, unknown> | undefined}
          hasAudiencePersona={hasAudiencePersona}
          apaExecutiveSummary={resultData.executive_summary as string | undefined}
          personas={resultData.personas as PersonaProfileFE[] | undefined}
          journeyMaps={resultData.journey_maps as BuyingJourneyMapFE[] | undefined}
          segmentMatrix={resultData.segment_matrix as Record<string, unknown> | undefined}
          hasTrendCultural={hasTrendCultural}
          trendReport={resultData.trend_report as TrendReportFE | undefined}
          scoredTrends={resultData.scored_trends as ScoredTrendFE[] | undefined}
          trendPersonaMatrix={resultData.trend_persona_matrix as { mappings: TrendPersonaMappingFE[] } | undefined}
          opportunityAlerts={resultData.opportunity_alerts as OpportunityAlertFE[] | undefined}
          viralPatterns={resultData.viral_patterns as ViralPatternProfileFE | undefined}
          culturalShifts={resultData.cultural_shifts as CulturalShiftFE[] | undefined}
          generationalInsights={resultData.generational_insights as GenerationalProfileFE[] | undefined}
          languageTrends={resultData.language_trends as LanguageTrendProfileFE | undefined}
          hasVoiceOfCustomer={hasVoiceOfCustomer}
          vocHealthScore={resultData.voc_health_score as number | undefined}
          operatingMode={resultData.operating_mode as string | undefined}
          dataCoverageScore={resultData.data_coverage_score as number | undefined}
          sentiment={resultData.sentiment as VoCSentimentFELocal | undefined}
          themes={resultData.themes as VoCThemeMapLocal | undefined}
          npsAnalysis={resultData.nps_analysis as VoCNPSLocal | undefined}
          painPointMatrix={resultData.pain_point_priority_matrix as { pain_points?: VoCPainPointLocal[]; methodology?: string } | undefined}
          strategyBridge={resultData.strategy_bridge as VoCStrategyBridgeLocal | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          confidenceScores={resultData.confidence_scores as Record<string, number> | undefined}
          confidenceScore={resultData.confidence_score as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {/* ── Single-agent fallbacks (when only 1 WF1 agent ran) ────── */}
      {!hasBrandDiscovery && hasMarketResearch && (
        <MarketResearchSection
          marketOverview={(resultData.market_overview ?? mraPayload?.market_overview) as string | undefined}
          marketSizing={(resultData.market_sizing ?? mraPayload?.market_sizing) as Record<string, unknown> | undefined}
          competitiveLandscape={(resultData.competitive_landscape ?? mraPayload?.competitive_landscape) as CompetitorEntry[] | undefined}
          industryTrends={(resultData.industry_trends ?? mraPayload?.industry_trends) as string[] | undefined}
          economicIndicators={(resultData.economic_indicators ?? mraPayload?.economic_indicators) as Record<string, unknown> | undefined}
          sources={(resultData.sources ?? mraPayload?.sources) as SourceEntry[] | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.market_research ?? resultData.confidence_score) as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {!hasBrandDiscovery && hasCompetitorIntelligence && (
        <CompetitorIntelligenceSection
          executiveSummary={resultData.executive_summary as string | undefined}
          competitors={resultData.competitors as CIACompetitorProfile[] | undefined}
          competitorMatrix={resultData.competitor_matrix as Record<string, Record<string, number>> | undefined}
          swotAnalyses={resultData.swot_analyses as SWOTAnalysis[] | undefined}
          positioningGaps={resultData.positioning_gaps as PositioningGap[] | undefined}
          benchmarkingReport={resultData.benchmarking_report as Record<string, unknown> | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.competitor_intelligence ?? resultData.confidence_score) as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {!hasBrandDiscovery && hasAudiencePersona && (
        <AudiencePersonaSection
          executiveSummary={resultData.executive_summary as string | undefined}
          personas={resultData.personas as PersonaProfileFE[] | undefined}
          journeyMaps={resultData.journey_maps as BuyingJourneyMapFE[] | undefined}
          segmentMatrix={resultData.segment_matrix as Record<string, unknown> | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.audience_persona ?? resultData.confidence_score) as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {!hasBrandDiscovery && hasTrendCultural && (
        <TrendCulturalSection
          trendReport={resultData.trend_report as TrendReportFE | undefined}
          scoredTrends={resultData.scored_trends as ScoredTrendFE[] | undefined}
          trendPersonaMatrix={resultData.trend_persona_matrix as { mappings: TrendPersonaMappingFE[] } | undefined}
          opportunityAlerts={resultData.opportunity_alerts as OpportunityAlertFE[] | undefined}
          viralPatterns={resultData.viral_patterns as ViralPatternProfileFE | undefined}
          culturalShifts={resultData.cultural_shifts as CulturalShiftFE[] | undefined}
          generationalInsights={resultData.generational_insights as GenerationalProfileFE[] | undefined}
          languageTrends={resultData.language_trends as LanguageTrendProfileFE | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.trend_cultural ?? resultData.confidence_score) as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {!hasBrandDiscovery && hasVoiceOfCustomer && (
        <VoiceOfCustomerSection
          vocHealthScore={resultData.voc_health_score as number | undefined}
          operatingMode={resultData.operating_mode as string | undefined}
          dataCoverageScore={resultData.data_coverage_score as number | undefined}
          sentiment={resultData.sentiment as VoCSentimentFELocal | undefined}
          themes={resultData.themes as VoCThemeMapLocal | undefined}
          npsAnalysis={resultData.nps_analysis as VoCNPSLocal | undefined}
          painPointMatrix={resultData.pain_point_priority_matrix as { pain_points?: VoCPainPointLocal[]; methodology?: string } | undefined}
          strategyBridge={resultData.strategy_bridge as VoCStrategyBridgeLocal | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.voice_of_customer ?? resultData.confidence_score) as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {/* ── Brand Positioning Dashboard ─────────────────────────────── */}
      {hasBrandArchitecture && (
        <BrandArchitectureSection
          recommendation={resultData.recommendation as BAARecommendation | undefined}
          hierarchy={resultData.hierarchy as BAAHierarchy | undefined}
          namingHierarchy={resultData.naming_hierarchy as BAANamingHierarchy | undefined}
          growthPath={resultData.growth_path as BAAGrowthPath | undefined}
          archStrategy={resultData.arch_strategy as Record<string, unknown> | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.brand_architecture ?? resultData.confidence_score) as number | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {/* ── Brand Personality Dashboard ─────────────────────────────── */}
      {hasBrandPersonality && (
        <BrandPersonalitySection
          aakerProfile={resultData.aaker_profile as BPVAakerProfile | undefined}
          archetype={resultData.archetype as BPVArchetype | undefined}
          valuesHierarchy={resultData.values_hierarchy as BPVValuesHierarchy | undefined}
          emotionalMap={resultData.emotional_map as BPVEmotionalMap | undefined}
          voiceMatrix={resultData.voice_matrix as BPVVoiceMatrix | undefined}
          characterBrief={resultData.character_brief as BPVCharacterBrief | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.brand_personality ?? resultData.confidence_score) as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {/* ── Brand Naming & Tagline Dashboard ────────────────────────── */}
      {hasBrandNaming && (
        <BrandNamingSection
          nameCandidates={resultData.name_candidates as NTANameCandidate[] | undefined}
          shortlistedNames={resultData.shortlisted_names as string[] | undefined}
          taglines={resultData.taglines as NTATagline[] | undefined}
          namingBrief={resultData.naming_brief as NTANamingBrief | undefined}
          availabilityResults={resultData.availability_results as Record<string, unknown> | undefined}
          scoringSummary={resultData.scoring_summary as Record<string, unknown> | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.brand_naming ?? resultData.confidence_score) as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {/* ── Brand Story & Narrative Dashboard ──────────────────────── */}
      {hasBrandStory && (
        <BrandStorySection
          originStory={resultData.origin_story as BSAOriginStory | undefined}
          missionVision={resultData.mission_vision as BSAMissionVision | undefined}
          pitches={resultData.pitches as BSAPitches | undefined}
          channelNarratives={resultData.channel_narratives as BSAChannelNarratives | undefined}
          storyStyleGuide={resultData.story_style_guide as BSAStoryStyleGuide | undefined}
          subbrandStories={resultData.subbrand_stories as BSASubBrandStory[] | undefined}
          narrativePackage={resultData.narrative_package as BSANarrativePackage | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.brand_story ?? resultData.confidence_score) as number | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {hasBrandPositioning && (
        <BrandPositioningSection
          recommendedPositioning={resultData.recommended_positioning as BPAPositioningStatement | undefined}
          positioningCandidates={resultData.positioning_candidates as BPAPositioningStatement[] | undefined}
          canvas={resultData.canvas as BPACanvas | undefined}
          perceptualMaps={resultData.perceptual_maps as BPAPerceptualMap[] | undefined}
          differentiation={resultData.differentiation as BPADifferentiation | undefined}
          strategy={resultData.strategy as BPAStrategy | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.brand_positioning ?? resultData.confidence_score) as number | undefined}
          sources={resultData.sources as SourceEntry[] | undefined}
          findings={findings}
          recommendations={recommendations}
        />
      )}

      {hasCampaignArchitecture && (
        <CampaignArchitectureSection
          blueprint={(caaNodeData?.blueprint ?? resultData.blueprint) as CAABlueprint | undefined}
          funnelMap={(caaNodeData?.funnel_map ?? resultData.funnel_map) as CAAFunnelMap | undefined}
          targetingSpecs={(caaNodeData?.targeting_specs ?? resultData.targeting_specs) as CAATargetingSpec[] | undefined}
          placementBudget={(caaNodeData?.placement_budget ?? resultData.placement_budget) as Record<string, unknown> | undefined}
          testPlan={(caaNodeData?.test_plan ?? resultData.test_plan) as CAATestPlan | undefined}
          kpiTargets={(caaNodeData?.kpi_targets ?? resultData.kpi_targets) as Record<string, Record<string, number>> | undefined}
          performanceProjections={(caaNodeData?.performance_projections ?? resultData.performance_projections) as CAAPerformanceProjections | undefined}
          riskAssessment={(caaNodeData?.risk_assessment ?? resultData.risk_assessment) as CAARiskAssessment | undefined}
          creativeBriefs={(caaNodeData?.creative_briefs ?? resultData.creative_briefs) as CAACreativeBrief[] | undefined}
          specialAdCategory={(caaNodeData?.special_ad_category ?? resultData.special_ad_category) as string | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.campaign_architecture ?? (caaNodeData?.confidence_score ?? resultData.confidence_score)) as number | undefined}
          findings={(caaNodeData?.findings as string[] | undefined) ?? findings}
          recommendations={(caaNodeData?.recommendations as string[] | undefined) ?? recommendations}
        />
      )}

      {hasCreativeGeneration && (
        <CreativeGenerationSection
          creativePackage={(cgaNodeData?.creative_package ?? resultData.creative_package) as CGACreativePackage | undefined}
          adSetPackages={(cgaNodeData?.ad_set_packages ?? resultData.ad_set_packages) as CGAAdSetPackage[] | undefined}
          adUnits={(cgaNodeData?.ad_units ?? resultData.ad_units) as CGACreativeUnit[] | undefined}
          generatedImages={(cgaNodeData?.generated_images ?? resultData.generated_images) as CGAGeneratedImage[] | undefined}
          hooks={(cgaNodeData?.hooks ?? resultData.hooks) as CGAHookVariant[] | undefined}
          copyVariants={(cgaNodeData?.copy_variants ?? resultData.copy_variants) as CGACopySet[] | undefined}
          ctas={(cgaNodeData?.ctas ?? resultData.ctas) as CGACTASet[] | undefined}
          complianceResults={(cgaNodeData?.compliance_results ?? resultData.compliance_results) as CGAComplianceResult[] | undefined}
          totalImagesGenerated={(cgaNodeData?.total_images_generated ?? resultData.total_images_generated) as number | undefined}
          imageGenCostUsd={(cgaNodeData?.image_gen_cost_usd ?? resultData.image_gen_cost_usd) as number | undefined}
          compliancePassRate={(cgaNodeData?.compliance_pass_rate ?? resultData.compliance_pass_rate) as number | undefined}
          creativeQualityScore={(cgaNodeData?.creative_quality_score ?? resultData.creative_quality_score) as number | undefined}
          confidenceScore={((resultData.confidence_scores as Record<string, number> | undefined)?.creative_generation ?? (cgaNodeData?.confidence_score ?? resultData.confidence_score)) as number | undefined}
          imageGenFailed={(cgaNodeData?.image_gen_failed ?? resultData.image_gen_failed) as boolean | undefined}
          findings={(cgaNodeData?.findings as string[] | undefined) ?? findings}
          recommendations={(cgaNodeData?.recommendations as string[] | undefined) ?? recommendations}
        />
      )}

      {/* Key findings — filter out raw JSON blobs (internal agent state) */}
      {!hasBrandDiscovery && !hasMarketResearch && !hasCompetitorIntelligence && !hasAudiencePersona && !hasTrendCultural && !hasVoiceOfCustomer && !hasBrandPositioning && !hasBrandArchitecture && !hasBrandPersonality && !hasBrandStory && !hasCampaignArchitecture && !hasCreativeGeneration && findings && findings.length > 0 && (() => {
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
      {!hasBrandDiscovery && !hasMarketResearch && !hasCompetitorIntelligence && !hasAudiencePersona && !hasTrendCultural && !hasVoiceOfCustomer && !hasBrandPositioning && !hasBrandArchitecture && !hasBrandPersonality && !hasBrandStory && !hasCampaignArchitecture && !hasCreativeGeneration && recommendations && recommendations.length > 0 && (
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
