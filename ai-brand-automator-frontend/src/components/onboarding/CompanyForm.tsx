'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';

export function CompanyForm() {
  const router = useRouter();
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    industry: '',
    targetAudience: '',
    coreProblem: '',
    website: '',
    address: '',
    city: '',
    stateProvince: '',
    postalCode: '',
    country: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [existingCompanyId, setExistingCompanyId] = useState<number | null>(null);

  // Load existing company data if it exists
  useEffect(() => {
    const loadExistingCompany = async () => {
      try {
        const response = await apiClient.get('/companies/');
        if (response.ok) {
          const data = await response.json();
          // API returns paginated data with results array
          const companies = data.results || [];
          if (companies.length > 0) {
            const company = companies[0]; // Get first company (one per tenant)
            setExistingCompanyId(company.id);
            setFormData({
              name: company.name || '',
              description: company.description || '',
              industry: company.industry || '',
              targetAudience: company.target_audience || '',
              coreProblem: company.core_problem || '',
              website: company.website || '',
              address: company.address || '',
              city: company.city || '',
              stateProvince: company.state_province || '',
              postalCode: company.postal_code || '',
              country: company.country || '',
            });
            // Store company ID for next steps
            localStorage.setItem('company_id', company.id.toString());
          }
        }
      } catch (error) {
        console.error('Error loading company:', error);
      }
    };
    loadExistingCompany();
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
      // Convert camelCase to snake_case for backend
      const apiData = {
        name: formData.name,
        description: formData.description,
        industry: formData.industry,
        target_audience: formData.targetAudience,
        core_problem: formData.coreProblem,
        website: formData.website,
        address: formData.address,
        city: formData.city,
        state_province: formData.stateProvince,
        postal_code: formData.postalCode,
        country: formData.country,
      };
      
      let response;
      if (existingCompanyId) {
        // Partial update existing company (PATCH preserves fields not sent)
        response = await apiClient.patch(`/companies/${existingCompanyId}/`, apiData);
      } else {
        // Create new company
        response = await apiClient.post('/companies/', apiData);
      }

      if (response.ok) {
        const data = await response.json();
        console.log('Company saved:', data);
        // Use known ID for updates; for new creates, get from response or refetch
        const companyId = existingCompanyId || data.id;
        if (companyId) {
          localStorage.setItem('company_id', companyId.toString());
        }
        router.push('/onboarding/step-2');
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to save company data');
      }
    } catch (error) {
      console.error('Company save error:', error);
      alert('Failed to save company data. Please try again.');
    }
    setIsLoading(false);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <label htmlFor="name" className="label-dark">
          Company Name *
        </label>
        <input
          type="text"
          id="name"
          name="name"
          required
          value={formData.name}
          onChange={handleChange}
          className="input-dark mt-1"
        />
      </div>

      <div>
        <label htmlFor="industry" className="label-dark">
          Industry *
        </label>
        <select
          id="industry"
          name="industry"
          required
          value={formData.industry}
          onChange={handleChange}
          className="select-dark mt-1"
        >
          <option value="">Select an industry</option>
          <option value="technology">Technology</option>
          <option value="healthcare">Healthcare</option>
          <option value="finance">Finance</option>
          <option value="retail">Retail</option>
          <option value="education">Education</option>
          <option value="other">Other</option>
        </select>
      </div>

      <div>
        <label htmlFor="description" className="label-dark">
          Company Description *
        </label>
        <textarea
          id="description"
          name="description"
          rows={4}
          required
          value={formData.description}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="Describe your company and what it does..."
        />
      </div>

      <div>
        <label htmlFor="targetAudience" className="label-dark">
          Target Audience
        </label>
        <textarea
          id="targetAudience"
          name="targetAudience"
          rows={3}
          value={formData.targetAudience}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="Who is your ideal customer?"
        />
      </div>

      <div>
        <label htmlFor="coreProblem" className="label-dark">
          Core Problem You Solve
        </label>
        <textarea
          id="coreProblem"
          name="coreProblem"
          rows={3}
          value={formData.coreProblem}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="What problem does your company solve for customers?"
        />
      </div>

      <div>
        <label htmlFor="website" className="label-dark">
          Website
        </label>
        <input
          type="url"
          id="website"
          name="website"
          value={formData.website}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="https://www.example.com"
        />
      </div>

      <div className="pt-2">
        <h3 className="label-dark mb-1">Physical Location</h3>
        <p className="text-xs text-brand-silver mb-3">
          If your brand serves a specific local area (e.g. a restaurant, clinic, or
          single-location store), provide the address below. The research, branding,
          and ad campaigns will be scoped exclusively to this local area.
        </p>
      </div>

      <div>
        <label htmlFor="address" className="label-dark">
          Street Address
        </label>
        <input
          type="text"
          id="address"
          name="address"
          value={formData.address}
          onChange={handleChange}
          className="input-dark mt-1"
          placeholder="123 Main Street"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label htmlFor="city" className="label-dark">
            City
          </label>
          <input
            type="text"
            id="city"
            name="city"
            value={formData.city}
            onChange={handleChange}
            className="input-dark mt-1"
          />
        </div>
        <div>
          <label htmlFor="stateProvince" className="label-dark">
            State / Province
          </label>
          <input
            type="text"
            id="stateProvince"
            name="stateProvince"
            value={formData.stateProvince}
            onChange={handleChange}
            className="input-dark mt-1"
          />
        </div>
        <div>
          <label htmlFor="postalCode" className="label-dark">
            Postal Code
          </label>
          <input
            type="text"
            id="postalCode"
            name="postalCode"
            value={formData.postalCode}
            onChange={handleChange}
            className="input-dark mt-1"
          />
        </div>
        <div>
          <label htmlFor="country" className="label-dark">
            Country
          </label>
          <input
            type="text"
            id="country"
            name="country"
            value={formData.country}
            onChange={handleChange}
            className="input-dark mt-1"
          />
        </div>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isLoading}
          className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Saving...' : existingCompanyId ? 'Update & Continue' : 'Next Step'}
        </button>
      </div>
    </form>
  );
}