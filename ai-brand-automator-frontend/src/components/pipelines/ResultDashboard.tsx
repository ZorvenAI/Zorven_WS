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
import { ClipboardCopy, Download, Check, ExternalLink } from 'lucide-react';
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

  // Route to specialized dashboard for Brand Equity / ISO pipelines
  const isBrandEquity =
    manifestName &&
    (/brand.?equity/i.test(manifestName) || /iso/i.test(manifestName));

  if (isBrandEquity) {
    return <BrandEquityDashboard resultData={resultData} />;
  }

  // ── Extract well-known keys ──────────────────────────────────────
  const summary = resultData.summary as string | undefined;
  const findings = resultData.findings as string[] | undefined;
  const recommendations = resultData.recommendations as string[] | undefined;
  const score = resultData.score as number | undefined;

  // ── Extract blog + social from node_results ──────────────────────
  const nodeResults = resultData.node_results as
    | Record<string, Record<string, unknown>>
    | undefined;
  const blogOutput = nodeResults?.blog_author as
    | Record<string, unknown>
    | undefined;
  const socialOutput = nodeResults?.social_promoter as
    | Record<string, unknown>
    | undefined;

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
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            Summary
          </h4>
          <MarkdownMessage content={summary} />
        </section>
      )}

      {/* Key findings */}
      {findings && findings.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
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
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
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
            <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider">
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
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-3">
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

      {/* Other sections (anything not already handled above) */}
      {otherEntries.map(([key, value]) => (
        <section key={key}>
          <h4 className="text-xs font-semibold text-brand-silver/60 uppercase tracking-wider mb-2">
            {sectionTitle(key)}
          </h4>
          {renderValue(value)}
        </section>
      ))}
    </div>
  );
}
