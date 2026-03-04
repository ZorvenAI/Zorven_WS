'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';

interface CompanyData {
  id: number;
  name: string;
  industry: string;
  description: string;
  target_audience: string;
  brand_voice: string;
  vision_statement: string;
  mission_statement: string;
  values: string; // Backend stores this as a text field, not array
  positioning_statement: string;
  color_palette_desc?: string;
  font_recommendations?: string;
  messaging_guide?: string;
}

export function OnboardingReview() {
  const router = useRouter();
  const [company, setCompany] = useState<CompanyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchCompanyData();
  }, []);

  const fetchCompanyData = async () => {
    try {
      const companyId = localStorage.getItem('company_id');
      if (!companyId) {
        setError('Company ID not found. Please start from step 1.');
        setLoading(false);
        return;
      }

      const response = await apiClient.get(`/companies/${companyId}/`);
      if (response.ok) {
        const data = await response.json();
        setCompany(data);
      } else {
        setError('Failed to load company data');
      }
    } catch (error) {
      console.error('Error fetching company data:', error);
      setError('An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateBrandStrategy = async () => {
    setGenerating(true);
    setError('');

    try {
      const companyId = localStorage.getItem('company_id');
      if (!companyId) {
        setError('Company ID not found');
        setGenerating(false);
        return;
      }

      const response = await apiClient.post(
        `/companies/${companyId}/generate_brand_strategy/`,
        {}
      );

      if (response.ok) {
        const data = await response.json();
        // Update company data with generated strategy
        setCompany(prev => prev ? { ...prev, ...data } : null);
        alert('Brand strategy generated successfully! Redirecting to AI Chat...');
        setTimeout(() => router.push('/chat'), 1500);
      } else {
        const errorData = await response.json();
        setError(errorData.message || 'Failed to generate brand strategy');
      }
    } catch (error) {
      console.error('Error generating brand strategy:', error);
      setError('An unexpected error occurred');
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerateBrandIdentity = async () => {
    setGenerating(true);
    setError('');

    try {
      const companyId = localStorage.getItem('company_id');
      if (!companyId) {
        setError('Company ID not found');
        setGenerating(false);
        return;
      }

      const response = await apiClient.post(
        `/companies/${companyId}/generate_brand_identity/`,
        {}
      );

      if (response.ok) {
        await response.json();
        alert('Brand identity generated successfully!');
        // Optionally fetch updated company data
        fetchCompanyData();
      } else {
        const errorData = await response.json();
        setError(errorData.message || 'Failed to generate brand identity');
      }
    } catch (error) {
      console.error('Error generating brand identity:', error);
      setError('An unexpected error occurred');
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-brand-electric"></div>
        <p className="mt-4 text-brand-silver/70">Loading your company data...</p>
      </div>
    );
  }

  if (!company) {
    return (
      <div className="text-center py-12">
        <p className="text-red-400">{error || 'Company data not found'}</p>
        <button
          onClick={() => router.push('/onboarding/step-1')}
          className="mt-4 btn-primary"
        >
          Start Over
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {error && (
        <div className="bg-red-900/30 border border-red-500/50 text-red-300 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Company Information */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h2 className="font-heading text-xl font-semibold text-white mb-4">Company Information</h2>
        <dl className="grid grid-cols-1 gap-4">
          <div>
            <dt className="text-sm font-medium text-brand-silver/70">Company Name</dt>
            <dd className="mt-1 text-sm text-white">{company.name}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-brand-silver/70">Industry</dt>
            <dd className="mt-1 text-sm text-white">{company.industry}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-brand-silver/70">Description</dt>
            <dd className="mt-1 text-sm text-white">{company.description}</dd>
          </div>
        </dl>
      </div>

      {/* Brand Details */}
      {company.brand_voice && (
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h2 className="font-heading text-xl font-semibold text-white mb-4">Brand Details</h2>
          <dl className="grid grid-cols-1 gap-4">
            <div>
              <dt className="text-sm font-medium text-brand-silver/70">Brand Voice</dt>
              <dd className="mt-1 text-sm text-white">{company.brand_voice}</dd>
            </div>
          </dl>
        </div>
      )}

      {/* Target Audience */}
      {company.target_audience && (
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h2 className="font-heading text-xl font-semibold text-white mb-4">Target Audience</h2>
          <p className="text-sm text-white">{company.target_audience}</p>
        </div>
      )}

      {/* AI-Generated Brand Strategy */}
      {company.vision_statement && (
        <div className="bg-brand-electric/10 border border-brand-electric/30 rounded-lg p-6">
          <h2 className="font-heading text-xl font-semibold text-white mb-4">
            🎯 AI-Generated Brand Strategy
          </h2>
          <dl className="grid grid-cols-1 gap-4">
            <div>
              <dt className="text-sm font-medium text-brand-electric">Vision Statement</dt>
              <dd className="mt-1 text-sm text-white">{company.vision_statement}</dd>
            </div>
            {company.mission_statement && (
              <div>
                <dt className="text-sm font-medium text-brand-electric">Mission Statement</dt>
                <dd className="mt-1 text-sm text-white">{company.mission_statement}</dd>
              </div>
            )}
            {company.values && company.values.length > 0 && (
              <div>
                <dt className="text-sm font-medium text-brand-electric">Core Values</dt>
                <dd className="mt-1">
                  <ul className="list-disc list-inside text-sm text-white">
                    {company.values.split(',').map((value, idx) => (
                      <li key={idx}>{value.trim()}</li>
                    ))}
                  </ul>
                </dd>
              </div>
            )}
            {company.positioning_statement && (
              <div>
                <dt className="text-sm font-medium text-brand-electric">Positioning Statement</dt>
                <dd className="mt-1 text-sm text-white">{company.positioning_statement}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {/* Brand Identity Visualization */}
      {(company.color_palette_desc || company.font_recommendations || company.messaging_guide) && (
        <div className="bg-brand-ghost/10 border border-brand-ghost/30 rounded-lg p-6">
          <h2 className="font-heading text-xl font-semibold text-white mb-4">🎨 Brand Identity</h2>
          <dl className="grid grid-cols-1 gap-4">
            {company.color_palette_desc && (
              <div>
                <dt className="text-sm font-medium text-brand-ghost">Color Palette</dt>
                <dd className="mt-1 text-sm text-white">
                  <ColorPaletteDisplay desc={company.color_palette_desc} />
                </dd>
              </div>
            )}
            {company.font_recommendations && (
              <div>
                <dt className="text-sm font-medium text-brand-ghost">Font Recommendations</dt>
                <dd className="mt-1 text-sm text-white">
                  <FontRecommendationsDisplay desc={company.font_recommendations} />
                </dd>
              </div>
            )}
            {company.messaging_guide && (
              <div>
                <dt className="text-sm font-medium text-brand-ghost">Messaging Guide</dt>
                <dd className="mt-1 text-sm text-white whitespace-pre-line">{company.messaging_guide}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex flex-col space-y-4 pt-6">
        {!company.vision_statement && (
          <button
            onClick={handleGenerateBrandStrategy}
            disabled={generating}
            className="w-full px-6 py-3 bg-brand-electric text-brand-midnight rounded-lg hover:bg-brand-electric/80 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors"
          >
            {generating ? 'Generating Brand Strategy...' : '✨ Generate Brand Strategy with AI'}
          </button>
        )}

        {company.vision_statement && (
          <button
            onClick={handleGenerateBrandIdentity}
            disabled={generating}
            className="w-full px-6 py-3 bg-brand-ghost text-white rounded-lg hover:bg-brand-ghost/80 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors"
          >
            {generating ? 'Generating Brand Identity...' : '🎨 Generate Brand Identity (Colors, Fonts)'}
          </button>
        )}

        <div className="flex justify-between">
          <button
            type="button"
            onClick={() => router.push('/onboarding/step-4')}
            className="btn-secondary"
          >
            Back
          </button>
          <button
            type="button"
            onClick={() => router.push('/chat')}
            className="btn-primary"
          >
            Complete & Start Chatting
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Visualization helpers ---
// Extract hex codes and color names from a string like "Primary: #0066CC, Secondary: #FF6600"
function ColorPaletteDisplay({ desc }: { desc: string }) {
  // Regex to find hex codes and their labels
  const colorRegex = /(\w+):\s*#([0-9a-fA-F]{6})/g;
  const matches = Array.from(desc.matchAll(colorRegex));
  if (matches.length === 0) {
    // fallback: just show the string
    return <span>{desc}</span>;
  }
  return (
    <div className="flex flex-wrap gap-4 items-center">
      {matches.map((m, i) => (
        <div key={i} className="flex flex-col items-center">
          <div
            className="w-10 h-10 rounded-full border border-white/20 mb-1 shadow-lg"
            style={{ backgroundColor: `#${m[2]}` }}
            title={m[1]}
          />
          <span className="text-xs text-brand-silver">{m[1]}</span>
          <span className="text-xs text-brand-silver/70">#{m[2]}</span>
        </div>
      ))}
    </div>
  );
}

// Display font recommendations, e.g. "Headings: Montserrat Bold, Body: Open Sans"
function FontRecommendationsDisplay({ desc }: { desc: string }) {
  // Try to extract font names and show a sample
  const fontRegex = /(\w+):\s*([\w\s]+(?:,\s*[\w\s]+)*)/g;
  const matches = Array.from(desc.matchAll(fontRegex));
  if (matches.length === 0) {
    return <span>{desc}</span>;
  }
  return (
    <div className="flex flex-wrap gap-6 items-center">
      {matches.map((m, i) => (
        <div key={i} className="flex flex-col items-start">
          <span className="text-xs text-brand-silver/70 font-semibold">{m[1]}</span>
          <span className="text-base text-white" style={{ fontFamily: m[2].split(',')[0] }}>{m[2]}</span>
        </div>
      ))}
    </div>
  );
}
