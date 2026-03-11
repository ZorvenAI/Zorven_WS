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
          content={JSON.stringify(resultData, null, 2)}
          title="Analysis Results"
          format="json"
        />
      </div>

      {/* Score badge (only when meaningful, i.e. > 0) */}
      {score !== undefined && score > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-brand-silver/60 uppercase tracking-wider">
            Score
          </span>
          <span className="inline-flex items-center rounded-full bg-brand-electric/20 px-3 py-1 text-sm font-bold text-brand-electric">
            {score}
          </span>
        </div>
      )}

      {/* Summary */}
      {summary && (
        <section>
          <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Summary
          </h4>
          <MarkdownMessage content={summary} />
        </section>
      )}

      {/* Key findings — filter out raw JSON blobs (internal agent state) */}
      {findings && findings.length > 0 && (() => {
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
