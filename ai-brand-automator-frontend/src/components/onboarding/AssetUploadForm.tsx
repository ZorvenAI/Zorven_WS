'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient, assetsApi } from '@/lib/api';
import { getPipelineStatusConfig, PipelineStatus } from '@/types/assets';
import { AllFilesModal } from '@/components/ui/AllFilesModal';
import { useWizardProvenance } from '@/hooks/useWizardProvenance';
import ProvenanceBadge from '@/components/onboarding/ProvenanceBadge';

const POLLING_INTERVAL = 5000;
const LIMIT_OPTIONS = [3, 6, 9] as const;

const SALES_CHANNEL_OPTIONS = [
  { value: 'online_store', label: 'Online Store' },
  { value: 'marketplace', label: 'Marketplace' },
  { value: 'retail', label: 'Retail' },
  { value: 'wholesale', label: 'Wholesale' },
  { value: 'direct', label: 'Direct Sales' },
  { value: 'social', label: 'Social Commerce' },
] as const;

const CURRENCY_OPTIONS = ['INR', 'USD', 'EUR', 'GBP', 'AUD', 'CAD'] as const;
const PERIOD_OPTIONS = ['monthly', 'quarterly', 'annually'] as const;

interface UploadedFile {
  id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  pipeline_status: PipelineStatus;
}

interface AssetsResponse {
  count: number;
  showing: number;
  has_more: boolean;
  results: UploadedFile[];
}

interface DuplicateConfirmation {
  file: File;
  fileType: string;
  existingAsset: {
    id: number;
    file_name: string;
    file_size: number;
    uploaded_at: string;
    pipeline_status: string;
  };
}

interface Competitor {
  name: string;
  url: string;
  notes: string;
}

interface ProductService {
  name: string;
  description: string;
  price_range: string;
}

interface SalesChannel {
  channel: string;
  notes: string;
}

interface DigitalPresence {
  website: string;
  instagram: string;
  facebook: string;
  linkedin: string;
  twitter: string;
  youtube: string;
}

interface BudgetRange {
  currency: string;
  min: string;
  max: string;
  period: string;
}

const emptyCompetitor = (): Competitor => ({ name: '', url: '', notes: '' });
const emptyProduct = (): ProductService => ({ name: '', description: '', price_range: '' });
const emptyPresence = (): DigitalPresence => ({
  website: '', instagram: '', facebook: '', linkedin: '', twitter: '', youtube: '',
});
const emptyBudget = (): BudgetRange => ({ currency: 'INR', min: '', max: '', period: 'monthly' });

function parseCompetitors(val: unknown): Competitor[] {
  if (!Array.isArray(val) || val.length === 0) return [emptyCompetitor()];
  return val.map((c: Record<string, unknown>) => ({
    name: String(c.name || ''),
    url: String(c.url || ''),
    notes: String(c.notes || ''),
  }));
}

function parseProducts(val: unknown): ProductService[] {
  if (!Array.isArray(val) || val.length === 0) return [emptyProduct()];
  return val.map((p: Record<string, unknown>) => ({
    name: String(p.name || ''),
    description: String(p.description || ''),
    price_range: String(p.price_range || ''),
  }));
}

function parseSalesChannels(val: unknown): SalesChannel[] {
  if (!Array.isArray(val)) return [];
  return val.map((s: Record<string, unknown>) => ({
    channel: String(s.channel || ''),
    notes: String(s.notes || ''),
  }));
}

function parsePresence(val: unknown): DigitalPresence {
  if (!val || typeof val !== 'object') return emptyPresence();
  const v = val as Record<string, unknown>;
  return {
    website: String(v.website || ''),
    instagram: String(v.instagram || ''),
    facebook: String(v.facebook || ''),
    linkedin: String(v.linkedin || ''),
    twitter: String(v.twitter || ''),
    youtube: String(v.youtube || ''),
  };
}

function parseBudget(val: unknown): BudgetRange {
  if (!val || typeof val !== 'object') return emptyBudget();
  const v = val as Record<string, unknown>;
  return {
    currency: String(v.currency || 'INR'),
    min: v.min != null ? String(v.min) : '',
    max: v.max != null ? String(v.max) : '',
    period: String(v.period || 'monthly'),
  };
}

function serializeCompetitors(items: Competitor[]): Array<Record<string, string>> | null {
  const valid = items.filter((c) => c.name.trim());
  if (valid.length === 0) return null;
  return valid.map((c) => {
    const obj: Record<string, string> = { name: c.name.trim() };
    if (c.url.trim()) obj.url = c.url.trim();
    if (c.notes.trim()) obj.notes = c.notes.trim();
    return obj;
  });
}

function serializeProducts(items: ProductService[]): Array<Record<string, string>> | null {
  const valid = items.filter((p) => p.name.trim());
  if (valid.length === 0) return null;
  return valid.map((p) => {
    const obj: Record<string, string> = { name: p.name.trim() };
    if (p.description.trim()) obj.description = p.description.trim();
    if (p.price_range.trim()) obj.price_range = p.price_range.trim();
    return obj;
  });
}

function serializeSalesChannels(items: SalesChannel[]): Array<Record<string, string>> | null {
  if (items.length === 0) return null;
  return items.map((s) => {
    const obj: Record<string, string> = { channel: s.channel };
    if (s.notes.trim()) obj.notes = s.notes.trim();
    return obj;
  });
}

function serializePresence(p: DigitalPresence): Record<string, string> | null {
  const obj: Record<string, string> = {};
  if (p.website.trim()) obj.website = p.website.trim();
  if (p.instagram.trim()) obj.instagram = p.instagram.trim();
  if (p.facebook.trim()) obj.facebook = p.facebook.trim();
  if (p.linkedin.trim()) obj.linkedin = p.linkedin.trim();
  if (p.twitter.trim()) obj.twitter = p.twitter.trim();
  if (p.youtube.trim()) obj.youtube = p.youtube.trim();
  return Object.keys(obj).length > 0 ? obj : null;
}

function serializeBudget(b: BudgetRange): Record<string, unknown> | null {
  const min = b.min.trim() ? Number(b.min) : null;
  if (min == null || isNaN(min)) return null;
  const obj: Record<string, unknown> = { currency: b.currency, min, period: b.period };
  const max = b.max.trim() ? Number(b.max) : null;
  if (max != null && !isNaN(max)) obj.max = max;
  return obj;
}

export function AssetUploadForm() {
  const router = useRouter();
  const { provenanceMap, editField, stepPath } = useWizardProvenance(4);

  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [displayLimit, setDisplayLimit] = useState<typeof LIMIT_OPTIONS[number]>(6);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [loadingUrlId, setLoadingUrlId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [showAllFiles, setShowAllFiles] = useState(false);
  const [duplicateConfirm, setDuplicateConfirm] = useState<DuplicateConfirmation | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const [brandAssetStatus, setBrandAssetStatus] = useState('');
  const [competitors, setCompetitors] = useState<Competitor[]>([emptyCompetitor()]);
  const [products, setProducts] = useState<ProductService[]>([emptyProduct()]);
  const [salesChannels, setSalesChannels] = useState<SalesChannel[]>([]);
  const [digitalPresence, setDigitalPresence] = useState<DigitalPresence>(emptyPresence());
  const [budgetRange, setBudgetRange] = useState<BudgetRange>(emptyBudget());
  const [savingMarket, setSavingMarket] = useState(false);
  const [marketError, setMarketError] = useState('');

  const initialMarket = useRef<Record<string, string>>({});

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
            setBrandAssetStatus(company.brand_asset_status || '');
            setCompetitors(parseCompetitors(company.competitors));
            setProducts(parseProducts(company.products_services));
            setSalesChannels(parseSalesChannels(company.sales_channels));
            setDigitalPresence(parsePresence(company.digital_presence));
            setBudgetRange(parseBudget(company.marketing_budget_range));
            initialMarket.current = {
              brand_asset_status: JSON.stringify(company.brand_asset_status || null),
              competitors: JSON.stringify(serializeCompetitors(parseCompetitors(company.competitors))),
              products_services: JSON.stringify(serializeProducts(parseProducts(company.products_services))),
              sales_channels: JSON.stringify(serializeSalesChannels(parseSalesChannels(company.sales_channels))),
              digital_presence: JSON.stringify(serializePresence(parsePresence(company.digital_presence))),
              marketing_budget_range: JSON.stringify(serializeBudget(parseBudget(company.marketing_budget_range))),
            };
          }
        }
      } catch (err) {
        console.error('Failed to load company data:', err);
      }
    };
    loadCompanyData();
  }, []);

  const fetchAssets = useCallback(async () => {
    try {
      const response = await apiClient.get(`/assets/?limit=${displayLimit}`);
      if (response.ok) {
        const data: AssetsResponse = await response.json();
        setUploadedFiles(data.results || []);
        setTotalCount(data.count || 0);
        setHasMore(data.has_more || false);
      }
    } catch (err) {
      console.error('Failed to load files:', err);
    }
  }, [displayLimit]);

  const hasPendingFiles = uploadedFiles.some(
    (f) => f.pipeline_status !== 'indexed' && f.pipeline_status !== 'failed',
  );

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  useEffect(() => {
    if (hasPendingFiles) {
      pollingRef.current = setInterval(() => {
        fetchAssets();
      }, POLLING_INTERVAL);
    } else if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [hasPendingFiles, fetchAssets]);

  const handleSaveMarket = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingMarket(true);
    setMarketError('');

    try {
      const companyId = localStorage.getItem('company_id');
      if (!companyId) {
        setMarketError('Company ID not found. Please start from step 1.');
        setSavingMarket(false);
        return;
      }

      const apiData: Record<string, unknown> = {
        brand_asset_status: brandAssetStatus || null,
        competitors: serializeCompetitors(competitors),
        products_services: serializeProducts(products),
        sales_channels: serializeSalesChannels(salesChannels),
        digital_presence: serializePresence(digitalPresence),
        marketing_budget_range: serializeBudget(budgetRange),
      };

      const response = await apiClient.patch(`/companies/${companyId}/`, apiData);

      if (response.ok) {
        const currentValues: Record<string, string> = {
          brand_asset_status: JSON.stringify(apiData.brand_asset_status),
          competitors: JSON.stringify(apiData.competitors),
          products_services: JSON.stringify(apiData.products_services),
          sales_channels: JSON.stringify(apiData.sales_channels),
          digital_presence: JSON.stringify(apiData.digital_presence),
          marketing_budget_range: JSON.stringify(apiData.marketing_budget_range),
        };

        const edits: Promise<void>[] = [];
        for (const key of Object.keys(currentValues)) {
          if (
            provenanceMap.has(key) &&
            apiData[key] != null &&
            currentValues[key] !== initialMarket.current[key]
          ) {
            edits.push(editField(key, apiData[key]));
          }
        }
        if (edits.length > 0) await Promise.allSettled(edits);

        initialMarket.current = currentValues;
        setMarketError('');
      } else {
        const errData = await response.json();
        setMarketError(errData.detail || 'Failed to save market data');
      }
    } catch (err) {
      console.error('Error saving market data:', err);
      setMarketError('An unexpected error occurred.');
    } finally {
      setSavingMarket(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setError('');

    try {
      const companyId = localStorage.getItem('company_id');
      if (!companyId) {
        setError('Company ID not found. Please start from step 1.');
        setUploading(false);
        return;
      }

      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('file_type', getFileType(file.type));

        const response = await apiClient.upload('/assets/upload/', formData);

        if (response.status === 409) {
          const dupData = await response.json();
          setDuplicateConfirm({
            file,
            fileType: getFileType(file.type),
            existingAsset: dupData.existing_asset,
          });
        } else if (response.ok) {
          const data = await response.json();
          setUploadedFiles((prev) => [...prev, data]);
        } else {
          const errorData = await response.json();
          setError(`Failed to upload ${file.name}: ${errorData.error || errorData.message || 'Unknown error'}`);
        }
      }
    } catch (err) {
      console.error('Error uploading files:', err);
      setError('An unexpected error occurred. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const getFileType = (mimeType: string): string => {
    if (mimeType.startsWith('image/')) return 'image';
    if (mimeType === 'application/pdf' || mimeType.includes('document')) return 'document';
    if (mimeType.startsWith('video/')) return 'video';
    return 'other';
  };

  const handleDuplicateReplace = async () => {
    if (!duplicateConfirm) return;
    const { file, fileType } = duplicateConfirm;
    setDuplicateConfirm(null);
    setError('');

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('file_type', fileType);
      formData.append('replace_existing', 'true');

      const response = await apiClient.upload('/assets/upload/', formData);
      if (response.ok) {
        await fetchAssets();
      } else {
        const errorData = await response.json();
        setError(`Failed to replace ${file.name}: ${errorData.error || errorData.message || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Error replacing file:', err);
      setError('Failed to replace file. Please try again.');
    }
  };

  const handleDuplicateSkip = () => {
    setDuplicateConfirm(null);
  };

  const handleSkip = () => {
    router.push(stepPath('/onboarding/step-5'));
  };

  const handleDelete = async (fileId: string, fileName: string) => {
    if (!confirm(`Are you sure you want to delete "${fileName}"?`)) {
      return;
    }

    setDeletingId(fileId);
    setError('');

    try {
      const response = await apiClient.delete(`/assets/${fileId}/`);
      if (response.ok) {
        setUploadedFiles((prev) => prev.filter((f) => f.id !== fileId));
      } else {
        const errorData = await response.json();
        setError(`Failed to delete ${fileName}: ${errorData.message || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Error deleting file:', err);
      setError(`Failed to delete ${fileName}. Please try again.`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleView = async (fileId: string) => {
    setLoadingUrlId(fileId);
    setError('');
    try {
      const signedUrls = await assetsApi.getSignedUrl(fileId);
      window.open(signedUrls.view_url, '_blank');
    } catch (err) {
      setError('Failed to get file URL');
      console.error('Error getting signed URL:', err);
    } finally {
      setLoadingUrlId(null);
    }
  };

  const handleDownload = async (fileId: string, fileName: string) => {
    setLoadingUrlId(fileId);
    setError('');
    try {
      const signedUrls = await assetsApi.getSignedUrl(fileId);
      const link = document.createElement('a');
      link.href = signedUrls.download_url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      setError('Failed to download file');
      console.error('Error downloading file:', err);
    } finally {
      setLoadingUrlId(null);
    }
  };

  const handleNext = () => {
    if (uploadedFiles.length === 0) {
      setError('Please upload at least one file or click Skip to continue.');
      return;
    }
    router.push(stepPath('/onboarding/step-5'));
  };

  const toggleSalesChannel = (channel: string) => {
    setSalesChannels((prev) => {
      const exists = prev.find((s) => s.channel === channel);
      if (exists) return prev.filter((s) => s.channel !== channel);
      return [...prev, { channel, notes: '' }];
    });
  };

  const updateSalesChannelNotes = (channel: string, notes: string) => {
    setSalesChannels((prev) =>
      prev.map((s) => (s.channel === channel ? { ...s, notes } : s)),
    );
  };

  return (
    <div className="space-y-8">
      {/* ── Market & Business Section ─────────────────────────────── */}
      <form onSubmit={handleSaveMarket} className="space-y-6">
        <div>
          <h3 className="text-lg font-semibold text-white mb-1">Market & Business</h3>
          <p className="text-xs text-brand-silver mb-4">
            Tell us about your market position, products, and budget.
          </p>
        </div>

        {marketError && (
          <div className="bg-red-900/30 border border-red-500/50 text-red-300 px-4 py-3 rounded-lg">
            {marketError}
          </div>
        )}

        <div>
          <label htmlFor="brandAssetStatus" className="label-dark">
            Brand Asset Status
            <ProvenanceBadge row={provenanceMap.get('brand_asset_status')} />
          </label>
          <select
            id="brandAssetStatus"
            value={brandAssetStatus}
            onChange={(e) => setBrandAssetStatus(e.target.value)}
            className="select-dark mt-1"
          >
            <option value="">Select status</option>
            <option value="none">None</option>
            <option value="basic">Basic (logo only)</option>
            <option value="partial">Partial (logo + some guidelines)</option>
            <option value="complete">Complete brand kit</option>
          </select>
        </div>

        {/* Competitors repeater */}
        <div>
          <label className="label-dark">
            Competitors
            <ProvenanceBadge row={provenanceMap.get('competitors')} />
          </label>
          <div className="mt-1 space-y-2">
            {competitors.map((comp, i) => (
              <div key={i} className="grid grid-cols-1 md:grid-cols-3 gap-2 items-start">
                <input
                  type="text"
                  value={comp.name}
                  onChange={(e) => {
                    const updated = [...competitors];
                    updated[i] = { ...comp, name: e.target.value };
                    setCompetitors(updated);
                  }}
                  className="input-dark"
                  placeholder="Name"
                />
                <input
                  type="text"
                  value={comp.url}
                  onChange={(e) => {
                    const updated = [...competitors];
                    updated[i] = { ...comp, url: e.target.value };
                    setCompetitors(updated);
                  }}
                  className="input-dark"
                  placeholder="Website URL"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={comp.notes}
                    onChange={(e) => {
                      const updated = [...competitors];
                      updated[i] = { ...comp, notes: e.target.value };
                      setCompetitors(updated);
                    }}
                    className="input-dark flex-1"
                    placeholder="Notes"
                  />
                  {competitors.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setCompetitors(competitors.filter((_, j) => j !== i))}
                      className="text-red-400 hover:text-red-300 px-2"
                      aria-label={`Remove competitor ${i + 1}`}
                    >
                      &times;
                    </button>
                  )}
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setCompetitors([...competitors, emptyCompetitor()])}
              className="text-sm text-brand-electric hover:text-brand-electric/80"
            >
              + Add competitor
            </button>
          </div>
        </div>

        {/* Products & Services repeater */}
        <div>
          <label className="label-dark">
            Products & Services
            <ProvenanceBadge row={provenanceMap.get('products_services')} />
          </label>
          <div className="mt-1 space-y-2">
            {products.map((prod, i) => (
              <div key={i} className="grid grid-cols-1 md:grid-cols-3 gap-2 items-start">
                <input
                  type="text"
                  value={prod.name}
                  onChange={(e) => {
                    const updated = [...products];
                    updated[i] = { ...prod, name: e.target.value };
                    setProducts(updated);
                  }}
                  className="input-dark"
                  placeholder="Name"
                />
                <input
                  type="text"
                  value={prod.description}
                  onChange={(e) => {
                    const updated = [...products];
                    updated[i] = { ...prod, description: e.target.value };
                    setProducts(updated);
                  }}
                  className="input-dark"
                  placeholder="Description"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={prod.price_range}
                    onChange={(e) => {
                      const updated = [...products];
                      updated[i] = { ...prod, price_range: e.target.value };
                      setProducts(updated);
                    }}
                    className="input-dark flex-1"
                    placeholder="Price range"
                  />
                  {products.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setProducts(products.filter((_, j) => j !== i))}
                      className="text-red-400 hover:text-red-300 px-2"
                      aria-label={`Remove product ${i + 1}`}
                    >
                      &times;
                    </button>
                  )}
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setProducts([...products, emptyProduct()])}
              className="text-sm text-brand-electric hover:text-brand-electric/80"
            >
              + Add product or service
            </button>
          </div>
        </div>

        {/* Sales Channels checkboxes */}
        <div>
          <label className="label-dark">
            Sales Channels
            <ProvenanceBadge row={provenanceMap.get('sales_channels')} />
          </label>
          <div className="mt-2 space-y-2">
            {SALES_CHANNEL_OPTIONS.map((opt) => {
              const active = salesChannels.find((s) => s.channel === opt.value);
              return (
                <div key={opt.value}>
                  <label className="flex items-center gap-2 text-sm text-brand-silver cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!active}
                      onChange={() => toggleSalesChannel(opt.value)}
                      className="rounded border-white/20 bg-white/5 text-brand-electric focus:ring-brand-electric"
                    />
                    {opt.label}
                  </label>
                  {active && (
                    <input
                      type="text"
                      value={active.notes}
                      onChange={(e) => updateSalesChannelNotes(opt.value, e.target.value)}
                      className="input-dark mt-1 ml-6 text-sm"
                      placeholder="Notes (optional)"
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Digital Presence */}
        <div>
          <label className="label-dark">
            Digital Presence
            <ProvenanceBadge row={provenanceMap.get('digital_presence')} />
          </label>
          <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-3">
            {(
              [
                ['website', 'Website URL'],
                ['instagram', 'Instagram handle'],
                ['facebook', 'Facebook page'],
                ['linkedin', 'LinkedIn page'],
                ['twitter', 'Twitter / X handle'],
                ['youtube', 'YouTube channel'],
              ] as const
            ).map(([key, placeholder]) => (
              <input
                key={key}
                type="text"
                value={digitalPresence[key]}
                onChange={(e) =>
                  setDigitalPresence({ ...digitalPresence, [key]: e.target.value })
                }
                className="input-dark"
                placeholder={placeholder}
              />
            ))}
          </div>
        </div>

        {/* Marketing Budget Range */}
        <div>
          <label className="label-dark">
            Marketing Budget Range
            <ProvenanceBadge row={provenanceMap.get('marketing_budget_range')} />
          </label>
          <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-3">
            <select
              value={budgetRange.currency}
              onChange={(e) => setBudgetRange({ ...budgetRange, currency: e.target.value })}
              className="select-dark"
            >
              {CURRENCY_OPTIONS.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <input
              type="number"
              value={budgetRange.min}
              onChange={(e) => setBudgetRange({ ...budgetRange, min: e.target.value })}
              className="input-dark"
              placeholder="Min"
              min="0"
            />
            <input
              type="number"
              value={budgetRange.max}
              onChange={(e) => setBudgetRange({ ...budgetRange, max: e.target.value })}
              className="input-dark"
              placeholder="Max"
              min="0"
            />
            <select
              value={budgetRange.period}
              onChange={(e) => setBudgetRange({ ...budgetRange, period: e.target.value })}
              className="select-dark"
            >
              {PERIOD_OPTIONS.map((p) => (
                <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={savingMarket}
            className="btn-primary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {savingMarket ? 'Saving...' : 'Save Market Info'}
          </button>
        </div>
      </form>

      {/* ── Divider ──────────────────────────────────────────────── */}
      <div className="border-t border-white/10" />

      {/* ── File Upload Section (unchanged) ──────────────────────── */}
      {error && (
        <div className="bg-red-900/30 border border-red-500/50 text-red-300 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      <div className="border-2 border-dashed border-white/20 rounded-lg p-8 text-center bg-white/5 hover:bg-white/10 hover:border-brand-electric/50 transition-colors">
        <div className="space-y-4">
          <div className="text-brand-silver/70">
            <svg
              className="mx-auto h-12 w-12 text-brand-electric/60"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
              aria-hidden="true"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div>
            <label
              htmlFor="file-upload"
              className="relative cursor-pointer rounded-md font-medium text-brand-electric hover:text-brand-electric/80"
            >
              <span>Upload files</span>
              <input
                id="file-upload"
                name="file-upload"
                type="file"
                className="sr-only"
                multiple
                onChange={handleFileUpload}
                accept="image/*,.pdf,.doc,.docx,.txt,video/*,.mp4,.mov"
                disabled={uploading}
              />
            </label>
            <p className="text-sm text-brand-silver/70 mt-1">
              or drag and drop
            </p>
          </div>
          <p className="text-xs text-brand-silver/50">
            PNG, JPG, PDF, MP4 up to 50MB each
          </p>
        </div>
      </div>

      {uploading && (
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric"></div>
          <p className="mt-2 text-sm text-brand-silver/70">Uploading files...</p>
        </div>
      )}

      {uploadedFiles.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-3">
              <h3 className="font-heading font-medium text-white">
                Uploaded Files
                <span className="ml-2 text-sm text-brand-silver/70">
                  ({uploadedFiles.length}{hasMore ? `/${totalCount}` : ''})
                </span>
              </h3>
              {hasPendingFiles && (
                <span className="text-xs text-brand-silver/70 animate-pulse">
                  Processing...
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-brand-silver/70">Show:</span>
                <select
                  value={displayLimit}
                  onChange={(e) => setDisplayLimit(Number(e.target.value) as typeof LIMIT_OPTIONS[number])}
                  className="px-2 py-1 text-xs rounded border border-white/20 bg-brand-dark text-white focus:outline-none focus:border-brand-electric"
                >
                  {LIMIT_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </div>
              {totalCount > displayLimit && (
                <button
                  onClick={() => setShowAllFiles(true)}
                  className="px-3 py-1 text-xs rounded border border-brand-electric/50 bg-brand-electric/20 text-brand-electric hover:bg-brand-electric/30 transition-colors"
                >
                  View All ({totalCount})
                </button>
              )}
            </div>
          </div>
          <ul className="divide-y divide-white/10 border border-white/10 rounded-lg bg-white/5">
            {uploadedFiles.map((file) => (
              <li key={file.id} className="px-4 py-3 flex items-center justify-between">
                <div className="flex items-center">
                  <span className="text-sm font-medium text-white">
                    {file.file_name}
                  </span>
                  <span className="ml-2 text-xs text-brand-silver/70">
                    ({(file.file_size / 1024).toFixed(1)} KB)
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  {(() => {
                    const statusConfig = getPipelineStatusConfig(file.pipeline_status || 'pending');
                    return (
                      <span className={`text-xs px-2 py-1 rounded ${statusConfig.bgColor} ${statusConfig.color}`}>
                        {statusConfig.icon} {statusConfig.label}
                      </span>
                    );
                  })()}
                  <span className="text-xs bg-brand-electric/20 text-brand-electric px-2 py-1 rounded">
                    {file.file_type}
                  </span>
                  {(file.pipeline_status === 'indexed' || file.pipeline_status === 'curated') && (
                    <button
                      type="button"
                      onClick={() => handleView(file.id)}
                      disabled={loadingUrlId === file.id}
                      className="text-brand-electric hover:text-brand-electric/80 disabled:opacity-50 transition-colors"
                      title="View file"
                    >
                      {loadingUrlId === file.id ? 'Loading...' : 'View'}
                    </button>
                  )}
                  {(file.pipeline_status === 'indexed' || file.pipeline_status === 'curated') && (
                    <button
                      type="button"
                      onClick={() => handleDownload(file.id, file.file_name)}
                      disabled={loadingUrlId === file.id}
                      className="text-brand-electric hover:text-brand-electric/80 disabled:opacity-50 transition-colors"
                      title="Download file"
                    >
                      Download
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleDelete(file.id, file.file_name)}
                    disabled={deletingId === file.id}
                    className="text-red-400 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    title="Delete file"
                  >
                    {deletingId === file.id ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex justify-between pt-6">
        <button
          type="button"
          onClick={() => router.push(stepPath('/onboarding/step-3'))}
          className="btn-secondary"
        >
          Back
        </button>
        <div className="space-x-3">
          <button
            type="button"
            onClick={handleSkip}
            className="btn-secondary"
          >
            Skip
          </button>
          <button
            type="button"
            onClick={handleNext}
            disabled={uploading}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next Step
          </button>
        </div>
      </div>

      <AllFilesModal
        isOpen={showAllFiles}
        onClose={() => {
          setShowAllFiles(false);
          fetchAssets();
        }}
        onDelete={async (fileId, fileName) => {
          await handleDelete(fileId, fileName);
        }}
      />

      {duplicateConfirm && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
          role="dialog"
          aria-modal="true"
          aria-labelledby="duplicate-dialog-title"
          onKeyDown={(e) => { if (e.key === 'Escape') handleDuplicateSkip(); }}
        >
          <div className="bg-brand-dark border border-white/20 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 id="duplicate-dialog-title" className="font-heading text-lg font-semibold text-white mb-2">
              File Already Exists
            </h3>
            <p className="text-brand-silver/80 text-sm mb-4">
              A file named <span className="font-medium text-white">&quot;{duplicateConfirm.existingAsset.file_name}&quot;</span> already exists
              (uploaded {new Date(duplicateConfirm.existingAsset.uploaded_at).toLocaleDateString()},
              status: {duplicateConfirm.existingAsset.pipeline_status}).
            </p>
            <p className="text-brand-silver/80 text-sm mb-6">
              Do you want to replace it with the new file?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={handleDuplicateSkip}
                className="px-4 py-2 text-sm rounded border border-white/20 text-brand-silver hover:bg-white/10 transition-colors"
              >
                Keep Existing
              </button>
              <button
                onClick={handleDuplicateReplace}
                className="px-4 py-2 text-sm rounded bg-brand-electric text-white hover:bg-brand-electric/80 transition-colors"
              >
                Replace File
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
