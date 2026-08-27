'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { useWizardProvenance } from '@/hooks/useWizardProvenance';
import ProvenanceBadge from '@/components/onboarding/ProvenanceBadge';

export function BrandForm() {
  const router = useRouter();
  const { provenanceMap, editField } = useWizardProvenance(2);

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    industry: '',
    targetAudience: '',
    coreProblem: '',
    brandVoice: '',
    visionStatement: '',
    missionStatement: '',
    values: '',
    positioningStatement: '',
    businessGoals: '',
  });
  const [isLoading, setIsLoading] = useState(false);
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
              brandVoice: company.brand_voice || '',
              visionStatement: company.vision_statement || '',
              missionStatement: company.mission_statement || '',
              values: company.values || '',
              positioningStatement: company.positioning_statement || '',
              businessGoals: company.business_goals || '',
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

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const companyId = localStorage.getItem('company_id');

      if (!companyId) {
        alert('Company ID not found. Please complete step 1 first.');
        router.push('/onboarding/step-1');
        return;
      }

      const apiData = {
        name: formData.name,
        description: formData.description,
        industry: formData.industry,
        target_audience: formData.targetAudience,
        core_problem: formData.coreProblem,
        brand_voice: formData.brandVoice,
        vision_statement: formData.visionStatement,
        mission_statement: formData.missionStatement,
        values: formData.values,
        positioning_statement: formData.positioningStatement,
        business_goals: formData.businessGoals,
      };

      const response = await apiClient.patch(`/companies/${companyId}/`, apiData);

      if (response.ok) {
        if (
          provenanceMap.has('business_goals') &&
          formData.businessGoals !== initialValues.current.businessGoals
        ) {
          await editField('business_goals', formData.businessGoals).catch(() => {});
        }

        router.push('/onboarding/step-3');
      } else {
        const error = await response.json();
        const errorMessage = error.detail ||
          (error.brand_voice && error.brand_voice[0]) ||
          JSON.stringify(error) ||
          'Failed to save brand data';
        alert(errorMessage);
      }
    } catch (error) {
      console.error('Brand update error:', error);
      alert('Failed to save brand data. Please try again.');
    }
    setIsLoading(false);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <label htmlFor="brandVoice" className="label-dark">
          Brand Voice *
        </label>
        <select
          id="brandVoice"
          name="brandVoice"
          required
          value={formData.brandVoice}
          onChange={handleChange}
          className="select-dark mt-1"
        >
          <option value="">Select brand voice</option>
          <option value="professional">Professional</option>
          <option value="friendly">Friendly</option>
          <option value="bold">Bold</option>
          <option value="authoritative">Authoritative</option>
          <option value="playful">Playful</option>
          <option value="innovative">Innovative</option>
          <option value="warm">Warm</option>
          <option value="technical">Technical</option>
        </select>
      </div>

      <div>
        <label htmlFor="visionStatement" className="label-dark">
          Vision Statement
        </label>
        <textarea
          id="visionStatement"
          name="visionStatement"
          rows={3}
          value={formData.visionStatement}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="What is your long-term vision?"
        />
      </div>

      <div>
        <label htmlFor="missionStatement" className="label-dark">
          Mission Statement
        </label>
        <textarea
          id="missionStatement"
          name="missionStatement"
          rows={3}
          value={formData.missionStatement}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="What is your mission?"
        />
      </div>

      <div>
        <label htmlFor="values" className="label-dark">
          Core Values
        </label>
        <textarea
          id="values"
          name="values"
          rows={3}
          value={formData.values}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="List your core values (comma-separated)"
        />
      </div>

      <div>
        <label htmlFor="positioningStatement" className="label-dark">
          Positioning Statement
        </label>
        <textarea
          id="positioningStatement"
          name="positioningStatement"
          rows={3}
          value={formData.positioningStatement}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="How do you position your brand?"
        />
      </div>

      <div>
        <label htmlFor="businessGoals" className="label-dark">
          Business Goals
          <ProvenanceBadge row={provenanceMap.get('business_goals')} />
        </label>
        <textarea
          id="businessGoals"
          name="businessGoals"
          rows={3}
          value={formData.businessGoals}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="What does your business want to achieve?"
        />
      </div>

      <div className="flex justify-between">
        <button
          type="button"
          onClick={() => router.push('/onboarding/step-1')}
          className="btn-secondary"
        >
          Previous
        </button>
        <button
          type="submit"
          disabled={isLoading}
          className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Saving...' : 'Next Step'}
        </button>
      </div>
    </form>
  );
}
