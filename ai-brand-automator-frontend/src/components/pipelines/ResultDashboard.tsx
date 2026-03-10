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
  const [copiedBlog, setCopiedBlog] = useState(false);
  const [ragSaveState, setRagSaveState] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');

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
  const odooOutput = nodeResults?.odoo_worker as
    | Record<string, unknown>
    | undefined;

  // Extract Odoo tool results from the worker agent's data field
  const odooData = odooOutput?.data as Record<string, unknown> | undefined;
  const odooToolResults = (odooData?.tool_results ?? []) as Array<{
    tool_name: string;
    data: Record<string, unknown>;
  }>;
  const odooFinalAnswer = odooData?.final_answer as string | undefined;
  const odooPersona = (odooOutput?.persona_used ??
    (odooOutput?.result_data as Record<string, unknown> | undefined)
      ?.persona) as string | undefined;

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

  // ── Blog copy / export handlers ──────────────────────────────────
  const handleCopyBlog = async () => {
    if (!blogContent) return;
    try {
      await navigator.clipboard.writeText(blogContent);
      setCopiedBlog(true);
      setTimeout(() => setCopiedBlog(false), 2000);
    } catch {
      // Clipboard not available
    }
  };

  const handleExportBlog = () => {
    if (!blogContent) return;
    let filename = 'blog-post.md';
    for (const line of blogContent.split('\n')) {
      if (line.startsWith('# ')) {
        const title = line.replace(/^#\s+/, '').trim();
        filename =
          title
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/-+$/, '') + '.md';
        break;
      }
    }
    const blob = new Blob([blogContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  /** Convert markdown to clean readable text for PDF storage. */
  const markdownToPlainText = (md: string): string => {
    return md
      .replace(/^#{1,6}\s+(.+)$/gm, '$1')       // headings → plain text
      .replace(/\*\*(.+?)\*\*/g, '$1')            // **bold** → text
      .replace(/\*(.+?)\*/g, '$1')                // *italic* → text
      .replace(/__(.+?)__/g, '$1')                // __bold__ → text
      .replace(/_(.+?)_/g, '$1')                  // _italic_ → text
      .replace(/`{3}[\s\S]*?`{3}/g, (m) =>        // code blocks → keep content
        m.replace(/^`{3}\w*\n?/gm, '').replace(/`{3}$/gm, ''))
      .replace(/`(.+?)`/g, '$1')                  // `inline code` → text
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1 ($2)') // [text](url) → text (url)
      .replace(/^>\s?/gm, '')                     // > blockquotes → plain
      .replace(/^[-*+]\s+/gm, '- ')               // bullet lists → dashes
      .replace(/^---+$/gm, '')                     // horizontal rules → remove
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')    // images → alt text
      .replace(/\n{3,}/g, '\n\n')                  // collapse excess blank lines
      .trim();
  };

  const handleSaveToRAG = async () => {
    if (!blogContent || ragSaveState === 'saving') return;
    setRagSaveState('saving');

    let title = 'Blog Post';
    for (const line of blogContent.split('\n')) {
      if (line.startsWith('# ')) {
        title = line.replace(/^#\s+/, '').trim();
        break;
      }
    }

    const plainText = markdownToPlainText(blogContent);

    try {
      const resp = await apiClient.post('/ai/chat/save-to-rag/', {
        content: plainText,
        title,
      });
      setRagSaveState(resp.ok ? 'saved' : 'error');
    } catch {
      setRagSaveState('error');
    }
    setTimeout(() => setRagSaveState('idle'), 3000);
  };

  return (
    <div className="glass-card p-6 space-y-6">
      {/* Header */}
      <h3 className="text-sm font-heading font-semibold text-white">
        Analysis Results
      </h3>

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

      {/* Key findings */}
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
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">
              Blog Post
            </h4>
            <div className="flex gap-2">
              <button
                onClick={handleCopyBlog}
                className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5"
              >
                {copiedBlog ? (
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <ClipboardCopy className="w-3.5 h-3.5" />
                )}
                {copiedBlog ? 'Copied' : 'Copy'}
              </button>
              <button
                onClick={handleExportBlog}
                className="btn-outline flex items-center gap-1.5 text-xs px-3 py-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                Export .md
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

      {/* ── Odoo ERP Results ─────────────────────────────────────── */}
      {odooOutput && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <h4 className="font-heading text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">
              Odoo ERP Results
            </h4>
            {odooPersona && (
              <span className="inline-flex items-center rounded-full bg-brand-electric/20 px-2 py-0.5 text-xs font-medium text-brand-electric capitalize">
                {odooPersona.replace(/_/g, ' ')}
              </span>
            )}
          </div>

          {/* ── Email Campaign KPI Dashboard ── */}
          {(() => {
            const campaignResults = odooToolResults.filter(
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
            const recipientResults = odooToolResults.filter(
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

          {odooFinalAnswer && (
            <div className="mb-4">
              <MarkdownMessage content={odooFinalAnswer} />
            </div>
          )}

          {/* ── Successful tool results as tables (skip failed and campaign results) ── */}
          {odooToolResults.length > 0 && (
            <div className="space-y-4">
              {odooToolResults
                .filter((tr) => tr.data?.success !== false && tr.tool_name !== 'marketing_create_campaign')
                .map((tr, idx) => {
                const innerResult = tr.data?.result as Record<string, unknown> | undefined;
                const records =
                  (innerResult?.records as Array<Record<string, unknown>>) ??
                  (tr.data?.records as Array<Record<string, unknown>>);
                if (records && records.length > 0) {
                  const columns = Object.keys(records[0]).filter(
                    (k) => k !== 'id' && !k.startsWith('_'),
                  );
                  return (
                    <div key={idx}>
                      <p className="text-xs text-brand-silver/60 mb-2 font-medium">
                        {tr.tool_name.replace(/_/g, ' ')}
                        <span className="ml-2 text-brand-silver/40">
                          ({records.length} records)
                        </span>
                      </p>
                      <div className="overflow-x-auto rounded-lg border border-white/10">
                        <table className="w-full text-sm text-left">
                          <thead className="bg-white/5 text-xs text-brand-silver/60 uppercase">
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
                // Fallback: render non-error results as JSON
                if (tr.data && !tr.data?.error) {
                  return (
                    <div key={idx}>
                      <p className="text-xs text-brand-silver/60 mb-1 font-medium">
                        {tr.tool_name.replace(/_/g, ' ')}
                      </p>
                      <pre className="text-xs text-brand-silver/80 bg-white/5 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                        {JSON.stringify(tr.data, null, 2)}
                      </pre>
                    </div>
                  );
                }
                return null;
              })}
            </div>
          )}
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
