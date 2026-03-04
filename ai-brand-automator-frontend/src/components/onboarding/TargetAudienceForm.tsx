'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';

export function TargetAudienceForm() {
  const router = useRouter();
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
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Load existing company data on mount
  useEffect(() => {
    const loadCompanyData = async () => {
      try {
        const response = await apiClient.get('/companies/');
        if (response.ok) {
          const data = await response.json();
          const companies = data.results || [];
          if (companies.length > 0) {
            const company = companies[0];
            // Store company ID in localStorage
            localStorage.setItem('company_id', company.id.toString());
            
            // Populate form with existing data (convert snake_case to camelCase)
            setFormData({
              name: company.name || '',
              description: company.description || '',
              industry: company.industry || '',
              targetAudience: company.target_audience || '',
              coreProblem: company.core_problem || '',
              demographics: company.demographics || '',
              psychographics: company.psychographics || '',
              painPoints: company.pain_points || '',
              desiredOutcomes: company.desired_outcomes || '',
            });
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

      // Update company with all required fields
      const apiData = {
        name: formData.name,
        description: formData.description,
        industry: formData.industry,
        target_audience: formData.targetAudience,
        core_problem: formData.coreProblem,
        demographics: formData.demographics,
        psychographics: formData.psychographics,
        pain_points: formData.painPoints,
        desired_outcomes: formData.desiredOutcomes,
      };

      const response = await apiClient.patch(
        `/companies/${companyId}/`,
        apiData
      );

      if (response.ok) {
        // Move to next step
        router.push('/onboarding/step-4');
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

      <div className="flex justify-between pt-6">
        <button
          type="button"
          onClick={() => router.push('/onboarding/step-2')}
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
