'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import MeetingEvidence from '@/components/onboarding/MeetingEvidence';

interface CompanyData {
  id: number;
  name: string;
  industry: string;
  description: string;
  target_audience?: string;
  core_problem?: string;
  website?: string;
  address?: string;
  city?: string;
  state_province?: string;
  postal_code?: string;
  country?: string;
  demographics?: string;
  psychographics?: string;
  pain_points?: string;
  desired_outcomes?: string;
  brand_voice: string;
  vision_statement: string;
  mission_statement: string;
  values: string; // Backend stores this as a text field, not array
  positioning_statement: string;
  tagline?: string;
  value_proposition?: string;
  elevator_pitch?: string;
  color_palette_desc?: string;
  font_recommendations?: string;
  messaging_guide?: string;
}

export function OnboardingReview({ sessionId = null }: { sessionId?: string | null }) {
  const router = useRouter();
  const [company, setCompany] = useState<CompanyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);
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

  const handleComplete = async () => {
    setCompleting(true);
    setError('');

    try {
      const companyId = localStorage.getItem('company_id');
      if (!companyId) {
        setError('Company ID not found');
        setCompleting(false);
        return;
      }

      // Generate the onboarding PDF and push it into the RAG pipeline
      await apiClient.post(
        `/companies/${companyId}/generate_onboarding_pdf/`,
        {}
      );

      // Navigate to chat regardless of PDF outcome
      router.push('/chat');
    } catch (err) {
      console.error('Error generating onboarding PDF:', err);
      // Still navigate — the PDF is a best-effort enhancement
      router.push('/chat');
    } finally {
      setCompleting(false);
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
          {company.target_audience && (
            <div>
              <dt className="text-sm font-medium text-brand-silver/70">Target Audience</dt>
              <dd className="mt-1 text-sm text-white">{company.target_audience}</dd>
            </div>
          )}
          {company.core_problem && (
            <div>
              <dt className="text-sm font-medium text-brand-silver/70">Core Problem You Solve</dt>
              <dd className="mt-1 text-sm text-white">{company.core_problem}</dd>
            </div>
          )}
          {company.website && (
            <div>
              <dt className="text-sm font-medium text-brand-silver/70">Website</dt>
              <dd className="mt-1 text-sm text-white">
                <a
                  href={company.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-brand-electric hover:underline"
                >
                  {company.website}
                </a>
              </dd>
            </div>
          )}
          {(company.address || company.city || company.state_province || company.postal_code || company.country) && (
            <div>
              <dt className="text-sm font-medium text-brand-silver/70">Physical Location</dt>
              <dd className="mt-1 text-sm text-white">
                {[company.address, company.city, company.state_province, company.postal_code, company.country]
                  .filter(Boolean)
                  .join(', ')}
              </dd>
            </div>
          )}
        </dl>
      </div>

      {/* Brand Details (captured in Step 2) */}
      {(company.brand_voice || company.vision_statement || company.mission_statement || company.values || company.positioning_statement) && (
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h2 className="font-heading text-xl font-semibold text-white mb-4">Brand Details</h2>
          <dl className="grid grid-cols-1 gap-4">
            {company.brand_voice && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Brand Voice</dt>
                <dd className="mt-1 text-sm text-white">{company.brand_voice}</dd>
              </div>
            )}
            {company.vision_statement && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Vision Statement</dt>
                <dd className="mt-1 text-sm text-white">{company.vision_statement}</dd>
              </div>
            )}
            {company.mission_statement && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Mission Statement</dt>
                <dd className="mt-1 text-sm text-white">{company.mission_statement}</dd>
              </div>
            )}
            {(() => {
              const valueItems = (company.values || '')
                .split(',')
                .map((v) => v.trim())
                .filter((v) => v.length > 0);
              if (valueItems.length === 0) return null;
              return (
                <div>
                  <dt className="text-sm font-medium text-brand-silver/70">Core Values</dt>
                  <dd className="mt-1">
                    <ul className="list-disc list-inside text-sm text-white">
                      {valueItems.map((value, idx) => (
                        <li key={idx}>{value}</li>
                      ))}
                    </ul>
                  </dd>
                </div>
              );
            })()}
            {company.positioning_statement && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Positioning Statement</dt>
                <dd className="mt-1 text-sm text-white">{company.positioning_statement}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {/* Target Audience */}
      {(company.target_audience || company.demographics || company.psychographics || company.pain_points || company.desired_outcomes) && (
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h2 className="font-heading text-xl font-semibold text-white mb-4">Target Audience</h2>
          <dl className="grid grid-cols-1 gap-4">
            {company.target_audience && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Primary Audience</dt>
                <dd className="mt-1 text-sm text-white">{company.target_audience}</dd>
              </div>
            )}
            {company.demographics && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Demographics</dt>
                <dd className="mt-1 text-sm text-white">{company.demographics}</dd>
              </div>
            )}
            {company.psychographics && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Psychographics</dt>
                <dd className="mt-1 text-sm text-white">{company.psychographics}</dd>
              </div>
            )}
            {company.pain_points && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Key Pain Points</dt>
                <dd className="mt-1 text-sm text-white">{company.pain_points}</dd>
              </div>
            )}
            {company.desired_outcomes && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Desired Outcomes</dt>
                <dd className="mt-1 text-sm text-white">{company.desired_outcomes}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {/* AI-Generated Brand Strategy */}
      {(company.tagline || company.value_proposition || company.elevator_pitch) && (
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h2 className="font-heading text-xl font-semibold text-white mb-4">AI Brand Strategy</h2>
          <dl className="grid grid-cols-1 gap-4">
            {company.tagline && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Tagline</dt>
                <dd className="mt-1 text-sm text-white">{company.tagline}</dd>
              </div>
            )}
            {company.value_proposition && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Value Proposition</dt>
                <dd className="mt-1 text-sm text-white">{company.value_proposition}</dd>
              </div>
            )}
            {company.elevator_pitch && (
              <div>
                <dt className="text-sm font-medium text-brand-silver/70">Elevator Pitch</dt>
                <dd className="mt-1 text-sm text-white">{company.elevator_pitch}</dd>
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

      {sessionId && <MeetingEvidence sessionId={sessionId} />}

      {/* Action Buttons */}
      <div className="flex flex-col space-y-4 pt-6">
        <div className="flex justify-between">
          <button
            type="button"
            onClick={() => router.push(sessionId ? `/onboarding/step-4?sessionId=${sessionId}` : '/onboarding/step-4')}
            className="btn-secondary"
          >
            Back
          </button>
          <button
            type="button"
            onClick={handleComplete}
            disabled={completing}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {completing ? 'Submitting...' : 'Submit'}
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
