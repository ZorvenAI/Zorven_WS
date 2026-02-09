import { env } from './env';
import { DuplicateFileError } from '@/lib/errors';

let isRefreshing = false;
let failedQueue: Array<{ resolve: (value: unknown) => void; reject: (reason?: Error) => void }> = [];

const processQueue = (error: Error | null = null, token: string | null = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });

  failedQueue = [];
};

const refreshAccessToken = async (): Promise<string | null> => {
  const refreshToken = typeof window !== 'undefined' ? localStorage.getItem('refresh_token') : null;

  if (!refreshToken) {
    return null;
  }

  try {
    const response = await fetch(env.getApiUrl('/auth/refresh/'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh: refreshToken }),
    });

    if (response.ok) {
      const data = await response.json();
      if (typeof window !== 'undefined') {
        localStorage.setItem('access_token', data.access);
        // If a new refresh token is provided, update it
        if (data.refresh) {
          localStorage.setItem('refresh_token', data.refresh);
        }
      }
      return data.access;
    }

    return null;
  } catch (error) {
    console.error('Token refresh failed:', error);
    return null;
  }
};

export const apiClient = {
  async request(endpoint: string, options: RequestInit = {}) {
    const url = env.getApiUrl(endpoint);
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

    // Separate headers from the rest of options to avoid override
    const { headers: optionHeaders, ...restOptions } = options;
    const isFormData = restOptions.body instanceof FormData;

    // Normalize all HeadersInit shapes (plain object, Headers instance,
    // or [string,string][]) into a single Headers object so callers can
    // pass any valid HeadersInit without being silently dropped.
    const mergedHeaders = new Headers(optionHeaders);

    // Only set Content-Type for non-FormData requests;
    // for FormData the browser must set it with the boundary
    if (!isFormData && !mergedHeaders.has('Content-Type')) {
      mergedHeaders.set('Content-Type', 'application/json');
    }
    if (token) {
      mergedHeaders.set('Authorization', `Bearer ${token}`);
    }

    const config: RequestInit = {
      headers: mergedHeaders,
      ...restOptions,
    };

    const response = await fetch(url, config);

    if (response.status === 401 && typeof window !== 'undefined') {
      // Token expired or invalid
      if (isRefreshing) {
        // Wait for the token refresh to complete
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then(token => {
            (config.headers as Headers).set('Authorization', `Bearer ${token}`);
            return fetch(url, config);
          })
          .catch(err => {
            return Promise.reject(err);
          });
      }

      isRefreshing = true;

      try {
        const newToken = await refreshAccessToken();

        if (newToken) {
          processQueue(null, newToken);
          // Retry original request with new token
          (config.headers as Headers).set('Authorization', `Bearer ${newToken}`);
          return fetch(url, config);
        } else {
          // Refresh failed, redirect to login
          processQueue(new Error('Token refresh failed'), null);
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/auth/login';
          return response;
        }
      } finally {
        isRefreshing = false;
      }
    }

    return response;
  },

  async get(endpoint: string) {
    return this.request(endpoint);
  },

  async post(endpoint: string, data: unknown) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async put(endpoint: string, data: unknown) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(endpoint: string) {
    return this.request(endpoint, {
      method: 'DELETE',
    });
  },

  async patch(endpoint: string, data: unknown) {
    return this.request(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  /**
   * Upload a file using FormData.
   * Does NOT set Content-Type — the browser adds the multipart boundary automatically.
   * Includes JWT auth and 401 auto-refresh like request().
   */
  async upload(endpoint: string, formData: FormData) {
    return this.request(endpoint, {
      method: 'POST',
      headers: {
        // Explicitly remove Content-Type so the browser sets it with boundary
      },
      body: formData,
    });
  },
};

// ==========================================
// Asset/File Browser API Types & Functions
// ==========================================

export interface AssetFile {
  id: string;
  file_name: string;
  file_type: 'image' | 'video' | 'document' | 'other';
  file_size: number;
  pipeline_status: 'pending' | 'ingested' | 'curated' | 'indexed' | 'failed';
  uploaded_at: string;
  gcs_path?: string;
}

export interface SignedUrlResponse {
  view_url: string;
  download_url: string;
  expires_at: string;
  file_name: string;
  file_type: string;
  file_size: number;
}

export interface AssetsListParams {
  page?: number;
  page_size?: number;
  limit?: number;
  search?: string;
  file_type?: string;
  status?: string;
  sort_by?: 'uploaded_at' | 'file_name' | 'file_size';
  sort_order?: 'asc' | 'desc';
}

export interface PaginatedAssetsResponse {
  count: number;
  total_pages: number;
  current_page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
  next: string | null;
  previous: string | null;
  results: AssetFile[];
  filters_applied: {
    search: string | null;
    file_type: string | null;
    status: string | null;
    sort_by: string;
    sort_order: string;
  };
}

export interface LimitedAssetsResponse {
  count: number;
  showing: number;
  has_more: boolean;
  results: AssetFile[];
  filters_applied: {
    search: string | null;
    file_type: string | null;
    status: string | null;
    sort_by: string;
    sort_order: string;
  };
}

export const assetsApi = {
  /**
   * Get paginated list of assets with optional filters
   */
  async getAssets(params: AssetsListParams = {}): Promise<PaginatedAssetsResponse | LimitedAssetsResponse> {
    const searchParams = new URLSearchParams();
    
    if (params.page) searchParams.set('page', params.page.toString());
    if (params.page_size) searchParams.set('page_size', params.page_size.toString());
    if (params.limit) searchParams.set('limit', params.limit.toString());
    if (params.search) searchParams.set('search', params.search);
    if (params.file_type) searchParams.set('file_type', params.file_type);
    if (params.status) searchParams.set('status', params.status);
    if (params.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params.sort_order) searchParams.set('sort_order', params.sort_order);

    const queryString = searchParams.toString();
    const endpoint = `/assets/${queryString ? `?${queryString}` : ''}`;
    
    const response = await apiClient.get(endpoint);
    if (!response.ok) {
      throw new Error('Failed to fetch assets');
    }
    return response.json();
  },

  /**
   * Get signed URLs for viewing/downloading a file
   * URLs expire in 15 minutes
   */
  async getSignedUrl(assetId: string): Promise<SignedUrlResponse> {
    const response = await apiClient.get(`/assets/${assetId}/signed-url/`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to get signed URL');
    }
    return response.json();
  },

  /**
   * Delete an asset
   */
  async deleteAsset(assetId: string): Promise<void> {
    const response = await apiClient.delete(`/assets/${assetId}/`);
    if (!response.ok) {
      throw new Error('Failed to delete asset');
    }
  },

  /**
   * Upload a new asset.
   * @param replaceExisting - If true, replaces an existing file with the same name.
   */
  async uploadAsset(file: File, fileType: string, replaceExisting = false): Promise<AssetFile> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('file_type', fileType);
    if (replaceExisting) {
      formData.append('replace_existing', 'true');
    }

    const response = await apiClient.upload('/assets/upload/', formData);

    if (response.status === 409) {
      const data = await response.json();
      throw new DuplicateFileError(
        data.message || 'A file with this name already exists.',
        data.existing_asset
      );
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || error.message || 'Failed to upload asset');
    }
    return response.json();
  },
};

// Subscription API types
export interface SubscriptionPlan {
  id: number;
  name: string;
  display_name: string;
  description: string;
  price: string;
  currency: string;
  max_brands: number;
  max_team_members: number;
  ai_generations_per_month: number;
  automation_enabled: boolean;
  priority_support: boolean;
  is_active: boolean;
}

export interface Subscription {
  id: number;
  plan: SubscriptionPlan;
  status: string;
  stripe_subscription_id: string;
  current_period_start: string;
  current_period_end: string;
  cancel_at_period_end: boolean;
}

export interface PaymentHistory {
  id: number;
  stripe_payment_intent_id: string;
  amount: string;
  currency: string;
  status: string;
  description: string;
  created_at: string;
}

// Paginated response type
interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Subscription API functions
export const subscriptionApi = {
  async getPlans(): Promise<SubscriptionPlan[]> {
    const response = await apiClient.get('/subscriptions/plans/');
    if (!response.ok) {
      throw new Error('Failed to fetch plans');
    }
    const data = await response.json();
    // Handle both paginated and non-paginated responses
    if (Array.isArray(data)) {
      return data;
    }
    // Paginated response
    return (data as PaginatedResponse<SubscriptionPlan>).results || [];
  },

  async getStatus(): Promise<Subscription | null> {
    const response = await apiClient.get('/subscriptions/status/');
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error('Failed to fetch subscription status');
    }
    return response.json();
  },

  async createCheckoutSession(planId: number): Promise<{ checkout_url: string }> {
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const response = await apiClient.post('/subscriptions/create-checkout-session/', {
      plan_id: planId,
      success_url: `${baseUrl}/subscription?success=true`,
      cancel_url: `${baseUrl}/subscription?canceled=true`,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to create checkout session');
    }
    return response.json();
  },

  async createPortalSession(): Promise<{ portal_url: string }> {
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const response = await apiClient.post('/subscriptions/create-portal-session/', {
      return_url: `${baseUrl}/billing`,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to create portal session');
    }
    return response.json();
  },

  async cancelSubscription(): Promise<{ message: string }> {
    const response = await apiClient.post('/subscriptions/cancel/', {});
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to cancel subscription');
    }
    return response.json();
  },

  async syncSubscription(): Promise<{ message: string; subscription: Subscription }> {
    const response = await apiClient.post('/subscriptions/sync/', {});
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to sync subscription');
    }
    return response.json();
  },

  async getPaymentHistory(): Promise<PaymentHistory[]> {
    const response = await apiClient.get('/subscriptions/payments/');
    if (!response.ok) {
      throw new Error('Failed to fetch payment history');
    }
    const data = await response.json();
    // Handle both paginated and non-paginated responses
    if (Array.isArray(data)) {
      return data;
    }
    return (data as PaginatedResponse<PaymentHistory>).results || [];
  },
};

// Google Business Profile types
export interface GoogleBusinessProfile {
  id: number;
  google_account_id: string | null;
  google_account_name: string | null;
  google_email: string | null;
  gbp_account_id: string | null;
  gbp_account_name: string | null;
  status: 'connected' | 'disconnected' | 'expired' | 'error' | 'pending_verification';
  is_mock: boolean;
  is_token_valid: boolean;
  created_at: string;
  updated_at: string;
  last_synced_at: string | null;
}

export interface GoogleBusinessLocation {
  id: number;
  location_id: string;
  business_name: string;
  primary_category: string;
  primary_category_id: string;
  additional_categories: string[];
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  phone_number: string;
  website_url: string;
  business_hours: Record<string, unknown>;
  special_hours: unknown[];
  verification_status: 'unverified' | 'pending' | 'verified' | 'failed';
  is_synced: boolean;
  full_address: string;
  created_at: string;
  updated_at: string;
}

export interface GoogleBusinessAccount {
  name: string;
  accountName: string;
  type: string;
  role: string;
  state: {
    status: string;
  };
}

export interface GoogleBusinessCategory {
  name: string;
  displayName: string;
}

export interface CreateLocationData {
  business_name: string;
  primary_category: string;
  address_line1: string;
  address_line2?: string;
  city: string;
  state: string;
  postal_code: string;
  country?: string;
  phone_number?: string;
  website_url?: string;
}

// Google Business Profile API functions
export const googleBusinessApi = {
  async getStatus(): Promise<GoogleBusinessProfile | null> {
    const response = await apiClient.get('/automation/google-business/status/');
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      return null;
    }
    const data = await response.json();
    return data.profile || null;
  },

  async connect(): Promise<{
    authorization_url: string | null;
    is_mock_mode: boolean;
    requires_approval?: boolean;
    message?: string;
    approval_url?: string;
  }> {
    const response = await apiClient.get('/automation/google-business/connect/');
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to initiate connection');
    }
    return response.json();
  },

  async testConnect(): Promise<{ message: string; profile: GoogleBusinessProfile }> {
    const response = await apiClient.post('/automation/google-business/test-connect/', {});
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to create test connection');
    }
    return response.json();
  },

  async disconnect(): Promise<{ message: string }> {
    const response = await apiClient.delete('/automation/google-business/disconnect/');
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to disconnect');
    }
    return response.json();
  },

  async getAccounts(): Promise<GoogleBusinessAccount[]> {
    const response = await apiClient.get('/automation/google-business/accounts/');
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to fetch accounts');
    }
    const data = await response.json();
    return data.accounts || [];
  },

  async selectAccount(accountId: string): Promise<{ message: string }> {
    const response = await apiClient.post('/automation/google-business/accounts/', {
      account_id: accountId,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to select account');
    }
    return response.json();
  },

  async getLocations(): Promise<GoogleBusinessLocation[]> {
    const response = await apiClient.get('/automation/google-business/locations/');
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to fetch locations');
    }
    const data = await response.json();
    return data.locations || [];
  },

  async createLocation(data: CreateLocationData): Promise<GoogleBusinessLocation> {
    const response = await apiClient.post('/automation/google-business/locations/', data);
    if (!response.ok) {
      const error = await response.json();
      // Handle DRF validation errors (field: [messages] format)
      if (typeof error === 'object' && !error.error) {
        const fieldErrors = Object.entries(error)
          .map(([field, msgs]) => `${field}: ${Array.isArray(msgs) ? msgs.join(', ') : msgs}`)
          .join('; ');
        throw new Error(fieldErrors || 'Validation failed');
      }
      throw new Error(error.error || error.detail || 'Failed to create location');
    }
    return response.json();
  },

  async updateLocation(
    locationId: string,
    data: Partial<CreateLocationData>
  ): Promise<GoogleBusinessLocation> {
    const response = await apiClient.put(
      `/automation/google-business/locations/${locationId}/`,
      data
    );
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to update location');
    }
    return response.json();
  },

  async deleteLocation(locationId: string): Promise<{ message: string }> {
    const response = await apiClient.delete(
      `/automation/google-business/locations/${locationId}/`
    );
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to delete location');
    }
    return response.json();
  },

  async searchCategories(query?: string): Promise<GoogleBusinessCategory[]> {
    const params = query ? `?q=${encodeURIComponent(query)}` : '';
    const response = await apiClient.get(`/automation/google-business/categories/${params}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to fetch categories');
    }
    const data = await response.json();
    return data.categories || [];
  },
};