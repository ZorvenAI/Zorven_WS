/**
 * ResultDashboard — renders the final result_data from a completed
 * analysis job as structured sections, key findings, and
 * recommendations.
 *
 * result_data is an opaque JSON object produced by the pipeline.
 * We render a best-effort structured view: if it contains familiar
 * keys (summary, findings, recommendations, sections) we format
 * them; otherwise we pretty-print the raw JSON.
 */

'use client';

import { useState } from 'react';
import { ClipboardCopy, Download, Check } from 'lucide-react';

interface ResultDashboardProps {
  resultData: Record<string, unknown>;
}

function renderValue(value: unknown): React.ReactNode {
  if (typeof value === 'string') return <p className="text-sm text-brand-silver">{value}</p>;
  if (typeof value === 'number' || typeof value === 'boolean')
    return <p className="text-sm text-brand-silver">{String(value)}</p>;
  if (Array.isArray(value)) {
    return (
      <ul className="list-disc list-inside space-y-1">
        {value.map((item, i) => (
          <li key={i} className="text-sm text-brand-silver">
            {typeof item === 'object' ? JSON.stringify(item) : String(item)}
          </li>
        ))}
      </ul>
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

export default function ResultDashboard({ resultData }: ResultDashboardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(resultData, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard not available (e.g. non-HTTPS)
    }
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(resultData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'analysis-results.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  // Attempt to extract well-known keys
  const summary = resultData.summary as string | undefined;
  const findings = resultData.findings as string[] | undefined;
  const recommendations = resultData.recommendations as string[] | undefined;
  const score = resultData.score as number | undefined;

  // Remaining keys (everything not already rendered above)
  const knownKeys = new Set(['summary', 'findings', 'recommendations', 'score']);
  const otherEntries = Object.entries(resultData).filter(
    ([k]) => !knownKeys.has(k),
  );

  return (
    <div className="glass-card p-6 space-y-6">
      {/* Header + actions */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-heading font-semibold text-white">
          Analysis Results
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

      {/* Score badge */}
      {score !== undefined && (
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

      {/* Other sections */}
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
