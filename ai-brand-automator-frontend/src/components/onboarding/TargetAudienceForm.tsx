'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { useWizardProvenance } from '@/hooks/useWizardProvenance';
import ProvenanceBadge from '@/components/onboarding/ProvenanceBadge';

function parseLanguages(val: unknown): string {
  if (Array.isArray(val)) return val.join(', ');
  return '';
}

function serializeLanguages(text: string): string[] | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return trimmed.split(',').map((s) => s.trim()).filter(Boolean);
}

function parseCustomerProof(val: unknown): string {
  if (!Array.isArray(val)) return '';
  return val
    .map((item: Record<string, unknown>) =>
      typeof item === 'object' && item !== null ? String(item.text || '') : String(item),
    )
    .filter(Boolean)
    .join('\n');
}

function serializeCustomerProof(
  text: string,
): Array<{ type: string; text: string }> | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return trimmed
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => ({ type: 'testimonial', text: line }));
}

export function TargetAudienceForm() {
  const router = useRouter();
  const { provenanceMap, editField, stepPath } = useWizardProvenance(3);

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    industry: '',
    targetAudience: '',
    coreProblem: '',
    demographics: '',
    psychographics: '',
    painPoints: '',
    desiredOutcomes: '',
    audienceLanguages: '',
    customerProof: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const initialValues = useRef<Record<string, string>>({});

  useEffect(() => {
    const loadCompanyData = async () => {
      try {
        const response = await apiClient.get('/companies/');
        if (response.ok) {
          const data = await response.json();
          const companies = data.results || [];
          if (companies.length > 0) {
            const company = companies[0];
            localStorage.setItem('company_id', company.id.toString());

            const loaded = {
              name: company.name || '',
              description: company.description || '',
              industry: company.industry || '',
              targetAudience: company.target_audience || '',
              coreProblem: company.core_problem || '',
              demographics: company.demographics || '',
              psychographics: company.psychographics || '',
              painPoints: company.pain_points || '',
              desiredOutcomes: company.desired_outcomes || '',
              audienceLanguages: parseLanguages(company.audience_languages),
              customerProof: parseCustomerProof(company.customer_proof),
            };
            setFormData(loaded);
            initialValues.current = { ...loaded };
          }
        }
      } catch (error) {
        console.error('Failed to load company data:', error);
      }
    };

    loadCompanyData();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const companyId = localStorage.getItem('company_id');
      if (!companyId) {
        setError('Company ID not found. Please start from step 1.');
        setLoading(false);
        return;
      }

      const apiData: Record<string, unknown> = {
        name: formData.name,
        description: formData.description,
        industry: formData.industry,
        target_audience: formData.targetAudience,
        core_problem: formData.coreProblem,
        demographics: formData.demographics,
        psychographics: formData.psychographics,
        pain_points: formData.painPoints,
        desired_outcomes: formData.desiredOutcomes,
        audience_languages: serializeLanguages(formData.audienceLanguages),
        customer_proof: serializeCustomerProof(formData.customerProof),
      };

      const response = await apiClient.patch(
        `/companies/${companyId}/`,
        apiData,
      );

      if (response.ok) {
        const provenanceEdits: Promise<void>[] = [];
        if (
          provenanceMap.has('audience_languages') &&
          formData.audienceLanguages !== initialValues.current.audienceLanguages
        ) {
          provenanceEdits.push(
            editField(
              'audience_languages',
              serializeLanguages(formData.audienceLanguages),
            ),
          );
        }
        if (
          provenanceMap.has('customer_proof') &&
          formData.customerProof !== initialValues.current.customerProof
        ) {
          provenanceEdits.push(
            editField(
              'customer_proof',
              serializeCustomerProof(formData.customerProof),
            ),
          );
        }
        await Promise.allSettled(provenanceEdits);

        router.push(stepPath('/onboarding/step-4'));
      } else {
        const errorData = await response.json();
        setError(errorData.message || 'Failed to save target audience data');
      }
    } catch (error) {
      console.error('Error saving target audience:', error);
      setError('An unexpected error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="bg-red-900/30 border border-red-500/50 text-red-300 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      <div>
        <label htmlFor="targetAudience" className="label-dark">
          Primary Target Audience *
        </label>
        <textarea
          id="targetAudience"
          rows={3}
          className="input-dark mt-1"
          value={formData.targetAudience}
          onChange={(e) => setFormData({ ...formData, targetAudience: e.target.value })}
          placeholder="e.g., Small business owners aged 30-50 who struggle with marketing automation"
          required
        />
        <p className="mt-1 text-sm text-brand-silver/70">
          Describe who your ideal customers are
        </p>
      </div>

      <div>
        <label htmlFor="demographics" className="label-dark">
          Demographics
        </label>
        <textarea
          id="demographics"
          rows={3}
          className="input-dark mt-1"
          value={formData.demographics}
          onChange={(e) => setFormData({ ...formData, demographics: e.target.value })}
          placeholder="e.g., Age range, gender, location, income level, education, occupation"
        />
        <p className="mt-1 text-sm text-brand-silver/70">
          Statistical characteristics of your audience
        </p>
      </div>

      <div>
        <label htmlFor="psychographics" className="label-dark">
          Psychographics
        </label>
        <textarea
          id="psychographics"
          rows={3}
          className="input-dark mt-1"
          value={formData.psychographics}
          onChange={(e) => setFormData({ ...formData, psychographics: e.target.value })}
          placeholder="e.g., Values, interests, lifestyle, personality traits, attitudes"
        />
        <p className="mt-1 text-sm text-brand-silver/70">
          Psychological characteristics and lifestyle
        </p>
      </div>

      <div>
        <label htmlFor="painPoints" className="label-dark">
          Key Pain Points *
        </label>
        <textarea
          id="painPoints"
          rows={3}
          className="input-dark mt-1"
          value={formData.painPoints}
          onChange={(e) => setFormData({ ...formData, painPoints: e.target.value })}
          placeholder="e.g., Wasting time on manual tasks, struggling to reach customers, limited marketing budget"
          required
        />
        <p className="mt-1 text-sm text-brand-silver/70">
          What problems does your audience face?
        </p>
      </div>

      <div>
        <label htmlFor="desiredOutcomes" className="label-dark">
          Desired Outcomes *
        </label>
        <textarea
          id="desiredOutcomes"
          rows={3}
          className="input-dark mt-1"
          value={formData.desiredOutcomes}
          onChange={(e) => setFormData({ ...formData, desiredOutcomes: e.target.value })}
          placeholder="e.g., Save time, grow revenue, reach more customers, streamline operations"
          required
        />
        <p className="mt-1 text-sm text-brand-silver/70">
          What do they want to achieve?
        </p>
      </div>

      <div>
        <label htmlFor="audienceLanguages" className="label-dark">
          Audience Languages
          <ProvenanceBadge row={provenanceMap.get('audience_languages')} />
        </label>
        <input
          type="text"
          id="audienceLanguages"
          className="input-dark mt-1"
          value={formData.audienceLanguages}
          onChange={(e) => setFormData({ ...formData, audienceLanguages: e.target.value })}
          placeholder="e.g., en-IN, kn-IN, hi-IN"
        />
        <p className="mt-1 text-sm text-brand-silver/70">
          BCP-47 language tags, comma-separated
        </p>
      </div>

      <div>
        <label htmlFor="customerProof" className="label-dark">
          Customer Proof
          <ProvenanceBadge row={provenanceMap.get('customer_proof')} />
        </label>
        <textarea
          id="customerProof"
          rows={4}
          className="input-dark mt-1"
          value={formData.customerProof}
          onChange={(e) => setFormData({ ...formData, customerProof: e.target.value })}
          placeholder="One testimonial, review, or case study per line"
        />
        <p className="mt-1 text-sm text-brand-silver/70">
          Testimonials, reviews, awards — one per line
        </p>
      </div>

      <div className="flex justify-between pt-6">
        <button
          type="button"
          onClick={() => router.push(stepPath('/onboarding/step-2'))}
          className="btn-secondary"
        >
          Back
        </button>
        <button
          type="submit"
          disabled={loading}
          className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Saving...' : 'Next Step'}
        </button>
      </div>
    </form>
  );
}
