'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

// ── Types ──

interface DimensionScore {
  name: string;
  score: number;
  weight: number;
  rationale: string;
  key_factors: string[];
}

interface Competitor {
  name: string;
  headquarters: string;
  estimated_score: number;
  strengths: string[];
  weaknesses: string[];
}

interface BrandEquityResult {
  company_name: string;
  overall_score: number;
  dimensions: DimensionScore[];
  competitors: Competitor[];
  formula_explanation: string;
  derivation: string;
  limitations: string[];
  recommendations: string[];
  methodology: string;
}

type PageState = 'form' | 'loading' | 'results' | 'error';

const BUSINESS_SIZES = [
  { value: 'micro', label: 'Micro (1-10 employees)' },
  { value: 'small', label: 'Small (11-50 employees)' },
  { value: 'medium', label: 'Medium (51-250 employees)' },
  { value: 'large', label: 'Large (251-1000 employees)' },
  { value: 'enterprise', label: 'Enterprise (1000+ employees)' },
];

const SCOPES = [
  { value: 'local', label: 'Local' },
  { value: 'regional', label: 'Regional' },
  { value: 'national', label: 'National' },
  { value: 'global', label: 'Global' },
];

function scoreColor(score: number): string {
  if (score >= 80) return 'text-brand-electric';
  if (score >= 60) return 'text-emerald-400';
  if (score >= 40) return 'text-yellow-400';
  return 'text-red-400';
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-brand-electric';
  if (score >= 60) return 'bg-emerald-400';
  if (score >= 40) return 'bg-yellow-400';
  return 'bg-red-400';
}

// ── Score Gauge (SVG circle) ──

function ScoreGauge({ score }: { score: number }) {
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="relative w-48 h-48 mx-auto">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 160 160">
        <circle cx="80" cy="80" r={radius} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="12" />
        <circle
          cx="80" cy="80" r={radius} fill="none"
          stroke="currentColor"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={`${scoreColor(score)} transition-all duration-1000 ease-out`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-5xl font-heading font-bold ${scoreColor(score)}`}>{score}</span>
        <span className="text-sm text-brand-silver/50">out of 100</span>
      </div>
    </div>
  );
}

// ── Dimension Card ──

function DimensionCard({ dim }: { dim: DimensionScore }) {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-heading text-white font-heading font-semibold text-sm">{dim.name}</h4>
        <span className={`text-lg font-bold ${scoreColor(dim.score)}`}>{dim.score}</span>
      </div>
      <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden mb-3">
        <div
          className={`h-full rounded-full transition-all duration-700 ${scoreBg(dim.score)}`}
          style={{ width: `${dim.score}%` }}
        />
      </div>
      <p className="text-xs text-brand-silver/60 mb-2">Weight: {(dim.weight * 100).toFixed(0)}%</p>
      <p className="text-sm text-brand-silver/80 mb-2">{dim.rationale}</p>
      {dim.key_factors.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {dim.key_factors.map((f, i) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-brand-silver/60">{f}</span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Page ──

export default function BrandEquityPage() {
  const [state, setState] = useState<PageState>('form');
  const [result, setResult] = useState<BrandEquityResult | null>(null);
  const [error, setError] = useState('');

  // Email export
  const [exportEmail, setExportEmail] = useState('');
  const [exportState, setExportState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [exportMessage, setExportMessage] = useState('');

  // Form fields
  const [companyName, setCompanyName] = useState('');
  const [address, setAddress] = useState('');
  const [website, setWebsite] = useState('');
  const [industryType, setIndustryType] = useState('');
  const [businessSize, setBusinessSize] = useState('');
  const [scope, setScope] = useState('');

  // Fade-in
  const [isLoaded, setIsLoaded] = useState(false);
  useEffect(() => { requestAnimationFrame(() => setIsLoaded(true)); }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState('loading');
    setError('');
    try {
      const apiUrl = process.env.NEXT_PUBLIC_BRAND_EQUITY_API_URL;
      if (!apiUrl) {
        throw new Error('Brand equity API is not configured. Please contact support.');
      }
      const res = await fetch(`${apiUrl}/v1/calculate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: companyName,
          address,
          website,
          industry_type: industryType,
          business_size: businessSize,
          scope,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: `Error ${res.status}` }));
        throw new Error(typeof errData.detail === 'string' ? errData.detail : `Error ${res.status}`);
      }
      const data: BrandEquityResult = await res.json();
      setResult(data);
      setState('results');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
      setState('error');
    }
  };

  return (
    <div className={`min-h-screen bg-brand-midnight transition-opacity duration-700 ${isLoaded ? 'opacity-100' : 'opacity-0'}`}>
      {/* Background gradient */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-gradient-to-br from-brand-ghost/10 via-transparent to-transparent rounded-full blur-3xl" />
        <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-gradient-to-tl from-brand-electric/5 via-transparent to-transparent rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <header className="relative z-50 px-4 sm:px-6 py-4 border-b border-white/5">
        <div className="max-w-5xl mx-auto flex justify-between items-center">
          <Link href="/" className="flex items-center gap-2 text-white font-heading font-bold text-lg">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-electric to-brand-ghost flex items-center justify-center">
              <span className="text-brand-midnight font-bold text-sm">B</span>
            </div>
            Brand Automator
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/auth/login" className="text-brand-silver/70 hover:text-white transition-colors text-sm hidden sm:block">
              Sign In
            </Link>
            <Link href="/auth/register" className="btn-primary text-sm px-4 py-2">
              Get Started Free
            </Link>
          </div>
        </div>
      </header>

      <main className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
        {/* Hero */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-electric/10 border border-brand-electric/20 mb-4">
            <span className="text-xs text-brand-electric font-medium">ISO 20671:2019</span>
          </div>
          <h1 className="font-heading text-3xl sm:text-5xl font-heading font-bold text-white mb-4">
            Brand Equity Calculator
          </h1>
          <p className="text-lg text-brand-silver/60 max-w-2xl mx-auto">
            Get a comprehensive brand equity analysis powered by Claude AI.
            Evaluate your brand across five ISO 20671 dimensions — completely free.
          </p>
        </div>

        {/* ── Form State ── */}
        {state === 'form' && (
          <form onSubmit={handleSubmit} className="glass-card p-6 sm:p-8 max-w-2xl mx-auto">
            <div className="space-y-5">
              <div>
                <label htmlFor="be-company" className="label-dark">Company Name *</label>
                <input
                  id="be-company"
                  type="text" required value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="e.g. Nike, Apple, your company"
                  className="input-dark"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div>
                  <label htmlFor="be-industry" className="label-dark">Industry Type *</label>
                  <input
                    id="be-industry"
                    type="text" required value={industryType}
                    onChange={(e) => setIndustryType(e.target.value)}
                    placeholder="e.g. Technology, Retail, Healthcare"
                    className="input-dark"
                  />
                </div>
                <div>
                  <label htmlFor="be-website" className="label-dark">Website</label>
                  <input
                    id="be-website"
                    type="text" value={website}
                    onChange={(e) => setWebsite(e.target.value)}
                    placeholder="https://example.com"
                    className="input-dark"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="be-address" className="label-dark">Address</label>
                <input
                  id="be-address"
                  type="text" value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="City, State, Country"
                  className="input-dark"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div>
                  <label htmlFor="be-size" className="label-dark">Business Size *</label>
                  <select
                    id="be-size"
                    required value={businessSize}
                    onChange={(e) => setBusinessSize(e.target.value)}
                    className="select-dark"
                  >
                    <option value="">Select size</option>
                    {BUSINESS_SIZES.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="be-scope" className="label-dark">Scope *</label>
                  <select
                    id="be-scope"
                    required value={scope}
                    onChange={(e) => setScope(e.target.value)}
                    className="select-dark"
                  >
                    <option value="">Select scope</option>
                    {SCOPES.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
            <button
              type="submit"
              disabled={!companyName || !industryType || !businessSize || !scope}
              className="btn-primary w-full mt-8 py-3 text-lg disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Calculate Brand Equity
            </button>
            <p className="text-center text-xs text-brand-silver/40 mt-3">
              No registration required. Results generated by Claude AI.
            </p>
          </form>
        )}

        {/* ── Loading State ── */}
        {state === 'loading' && (
          <div className="glass-card p-12 max-w-2xl mx-auto text-center">
            <div className="relative w-20 h-20 mx-auto mb-6">
              <div className="absolute inset-0 rounded-full border-4 border-white/10" />
              <div className="absolute inset-0 rounded-full border-4 border-brand-electric border-t-transparent animate-spin" />
            </div>
            <h3 className="font-heading text-xl font-heading font-bold text-white mb-2">
              Analyzing Brand Equity
            </h3>
            <p className="text-brand-silver/60">
              Claude AI is evaluating {companyName} across five ISO 20671 dimensions.
              This typically takes 15-30 seconds...
            </p>
          </div>
        )}

        {/* ── Error State ── */}
        {state === 'error' && (
          <div className="glass-card p-8 max-w-2xl mx-auto text-center border-red-500/30">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-500/20 flex items-center justify-center">
              <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <h3 className="font-heading text-xl font-heading font-bold text-white mb-2">Analysis Failed</h3>
            <p className="text-brand-silver/60 mb-6">{error}</p>
            <button onClick={() => setState('form')} className="btn-primary px-6 py-2.5">
              Try Again
            </button>
          </div>
        )}

        {/* ── Results State ── */}
        {state === 'results' && result && (
          <div className="space-y-8">
            {/* Overall Score */}
            <div className="glass-card p-8 text-center">
              <p className="text-sm text-brand-silver/50 mb-2">{result.methodology}</p>
              <h2 className="font-heading text-2xl font-heading font-bold text-white mb-6">
                {result.company_name} — Brand Equity Score
              </h2>
              <ScoreGauge score={result.overall_score} />
            </div>

            {/* Dimension Breakdown */}
            <div>
              <h3 className="font-heading text-lg font-heading font-semibold text-white mb-4">Dimension Breakdown</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {result.dimensions.map((dim, i) => (
                  <DimensionCard key={i} dim={dim} />
                ))}
              </div>
            </div>

            {/* Competitor Analysis */}
            {result.competitors && result.competitors.length > 0 && (
              <div>
                <h3 className="font-heading text-lg font-heading font-semibold text-white mb-4">Competitor Analysis</h3>
                <div className="space-y-4">
                  {result.competitors.map((comp, i) => (
                    <div key={i} className="glass-card p-5">
                      <div className="flex items-center justify-between mb-1">
                        <div>
                          <h4 className="font-heading text-white font-heading font-semibold">{comp.name}</h4>
                          {comp.headquarters && (
                            <p className="text-xs text-brand-silver/40 mt-0.5">{comp.headquarters}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-brand-silver/50">Estimated Score</span>
                          <span className={`text-lg font-bold ${scoreColor(comp.estimated_score)}`}>
                            {comp.estimated_score}
                          </span>
                        </div>
                      </div>
                      <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden mb-4">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${scoreBg(comp.estimated_score)}`}
                          style={{ width: `${comp.estimated_score}%` }}
                        />
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {comp.strengths.length > 0 && (
                          <div>
                            <p className="text-xs text-emerald-400 font-medium mb-1.5">Strengths</p>
                            <ul className="space-y-1">
                              {comp.strengths.map((s, j) => (
                                <li key={j} className="text-sm text-brand-silver/70 flex items-start gap-1.5">
                                  <span className="text-emerald-400 mt-0.5 shrink-0">+</span>
                                  {s}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {comp.weaknesses.length > 0 && (
                          <div>
                            <p className="text-xs text-red-400 font-medium mb-1.5">Weaknesses</p>
                            <ul className="space-y-1">
                              {comp.weaknesses.map((w, j) => (
                                <li key={j} className="text-sm text-brand-silver/70 flex items-start gap-1.5">
                                  <span className="text-red-400 mt-0.5 shrink-0">-</span>
                                  {w}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Formula Explanation */}
            {result.formula_explanation && (
              <div className="glass-card p-6">
                <h3 className="font-heading text-lg font-heading font-semibold text-white mb-3">How We Calculated This</h3>
                <p className="text-sm text-brand-silver/70 font-mono leading-relaxed">{result.formula_explanation}</p>
              </div>
            )}

            {/* Derivation */}
            {result.derivation && (
              <div className="glass-card p-6">
                <h3 className="font-heading text-lg font-heading font-semibold text-white mb-3">Step-by-Step Derivation</h3>
                <p className="text-sm text-brand-silver/70 whitespace-pre-line leading-relaxed">{result.derivation}</p>
              </div>
            )}

            {/* Limitations */}
            {result.limitations.length > 0 && (
              <div className="glass-card p-6 border-yellow-500/20">
                <h3 className="font-heading text-lg font-heading font-semibold text-yellow-400 mb-3">Limitations</h3>
                <ul className="space-y-2">
                  {result.limitations.map((lim, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-brand-silver/70">
                      <span className="text-yellow-400 mt-0.5">&#9888;</span>
                      {lim}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Recommendations */}
            {result.recommendations.length > 0 && (
              <div className="glass-card p-6">
                <h3 className="font-heading text-lg font-heading font-semibold text-brand-mint mb-3">Recommendations</h3>
                <ul className="space-y-3">
                  {result.recommendations.map((rec, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm text-brand-silver/80">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-brand-mint/20 flex items-center justify-center text-brand-mint text-xs font-bold">
                        {i + 1}
                      </span>
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Email Export */}
            <div className="glass-card p-6 sm:p-8">
              <h3 className="font-heading text-lg font-heading font-semibold text-white mb-2">Export Report</h3>
              <p className="text-sm text-brand-silver/60 mb-4">
                Enter your email to receive the full brand equity report as a PDF.
              </p>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (!exportEmail || !result) return;
                  setExportState('sending');
                  setExportMessage('');
                  try {
                    const apiUrl = process.env.NEXT_PUBLIC_BRAND_EQUITY_API_URL;
                    if (!apiUrl) throw new Error('API not configured');
                    const res = await fetch(`${apiUrl}/v1/export`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ email: exportEmail, result }),
                    });
                    const data = await res.json();
                    if (res.ok && data.success) {
                      setExportState('sent');
                      setExportMessage(data.message || 'Report sent!');
                    } else {
                      setExportState('error');
                      setExportMessage(data.detail || 'Failed to send report.');
                    }
                  } catch {
                    setExportState('error');
                    setExportMessage('Failed to send report. Please try again.');
                  }
                }}
                className="flex flex-col sm:flex-row gap-3"
              >
                <label htmlFor="be-export-email" className="sr-only">Email address for PDF report</label>
                <input
                  type="email"
                  required
                  value={exportEmail}
                  onChange={(e) => { setExportEmail(e.target.value); if (exportState !== 'idle') setExportState('idle'); }}
                  placeholder="your@email.com"
                  className="input-dark flex-1"
                  id="be-export-email"
                />
                <button
                  type="submit"
                  disabled={exportState === 'sending' || exportState === 'sent' || !exportEmail}
                  className="btn-primary px-6 py-2.5 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {exportState === 'sending' && (
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  )}
                  {exportState === 'sent' ? 'Sent!' : exportState === 'sending' ? 'Sending...' : 'Send PDF Report'}
                </button>
              </form>
              {exportMessage && (
                <p className={`text-sm mt-3 ${exportState === 'sent' ? 'text-brand-mint' : 'text-red-400'}`}>
                  {exportMessage}
                </p>
              )}
            </div>

            {/* Registration CTA */}
            <div className="glass-card p-8 sm:p-10 text-center border-brand-electric/20">
              <h3 className="font-heading text-2xl sm:text-3xl font-heading font-bold text-white mb-4">
                Ready to Implement These Recommendations?
              </h3>
              <p className="text-brand-silver/60 mb-8 max-w-xl mx-auto">
                Sign up for AI Brand Automator to get AI-powered brand building tools,
                automated social media management, and continuous brand equity monitoring.
                We&apos;ll help you turn these insights into action.
              </p>
              <Link
                href="/auth/register"
                className="inline-flex items-center gap-2 bg-gradient-to-r from-brand-electric to-brand-ghost text-brand-midnight font-bold px-8 py-4 rounded-xl text-lg transition-all hover:shadow-[0_0_40px_rgba(0,245,255,0.4)] hover:-translate-y-1"
              >
                Start Your Free Trial
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </Link>
            </div>

            {/* Calculate Another */}
            <div className="text-center">
              <button
                onClick={() => { setState('form'); setResult(null); }}
                className="text-brand-silver/50 hover:text-brand-silver transition-colors text-sm underline underline-offset-4"
              >
                Calculate another company
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-white/5 py-8">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="text-xs text-brand-silver/40">
            Powered by Claude AI &middot; ISO 20671:2019 methodology
          </p>
          <div className="flex gap-4 text-xs text-brand-silver/40">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <Link href="/auth/register" className="hover:text-white transition-colors">Sign Up</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
