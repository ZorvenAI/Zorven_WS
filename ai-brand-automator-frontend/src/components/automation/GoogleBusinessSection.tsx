'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  googleBusinessApi,
  GoogleBusinessProfile,
  GoogleBusinessLocation,
  GoogleBusinessAccount,
  GoogleBusinessCategory,
  CreateLocationData,
} from '@/lib/api';

interface GoogleBusinessSectionProps {
  onMessage: (message: { type: 'success' | 'error' | 'warning'; text: string }) => void;
}

export default function GoogleBusinessSection({ onMessage }: GoogleBusinessSectionProps) {
  // Hooks for handling mock OAuth callback
  const searchParams = useSearchParams();
  
  // State
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [profile, setProfile] = useState<GoogleBusinessProfile | null>(null);
  const [accounts, setAccounts] = useState<GoogleBusinessAccount[]>([]);
  const [locations, setLocations] = useState<GoogleBusinessLocation[]>([]);
  const [categories, setCategories] = useState<GoogleBusinessCategory[]>([]);

  // UI State
  const [showAccountSelector, setShowAccountSelector] = useState(false);
  const [showCreateLocation, setShowCreateLocation] = useState(false);
  const [showLocations, setShowLocations] = useState(false);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [loadingLocations, setLoadingLocations] = useState(false);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const [showCustomCategory, setShowCustomCategory] = useState(false);
  const [showApiNotConfigured, setShowApiNotConfigured] = useState(false);
  const [apiApprovalUrl, setApiApprovalUrl] = useState<string | null>(null);

  // Form state for creating location
  const [newLocation, setNewLocation] = useState<CreateLocationData>({
    business_name: '',
    primary_category: '',
    address_line1: '',
    address_line2: '',
    city: '',
    state: '',
    postal_code: '',
    country: 'US',
    phone_number: '',
    website_url: '',
  });

  // Fetch profile status
  const fetchStatus = useCallback(async () => {
    try {
      const data = await googleBusinessApi.getStatus();
      setProfile(data);
    } catch (error) {
      console.error('Failed to fetch GBP status:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle OAuth callback from URL params (for real OAuth flow)
  useEffect(() => {
    const googleBusinessConnected = searchParams.get('google_business');
    const error = searchParams.get('error');
    
    if (googleBusinessConnected === 'connected') {
      // Real OAuth callback success
      onMessage({ type: 'success', text: 'Connected to Google Business Profile!' });
      window.history.replaceState({}, '', '/automation');
      fetchStatus();
    } else if (error) {
      // OAuth error
      const message = searchParams.get('message') || 'Failed to connect to Google Business Profile';
      onMessage({ type: 'error', text: decodeURIComponent(message) });
      window.history.replaceState({}, '', '/automation');
    }
  }, [searchParams, onMessage, fetchStatus]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Fetch accounts when connected
  const fetchAccounts = useCallback(async () => {
    if (!profile?.status || profile.status !== 'connected') return;

    setLoadingAccounts(true);
    try {
      const data = await googleBusinessApi.getAccounts();
      setAccounts(data);
    } catch (error) {
      console.error('Failed to fetch GBP accounts:', error);
      onMessage({ type: 'error', text: 'Failed to fetch Google Business accounts' });
    } finally {
      setLoadingAccounts(false);
    }
  }, [profile?.status, onMessage]);

  // Fetch locations when account is selected
  const fetchLocations = useCallback(async () => {
    if (!profile?.gbp_account_id) {
      console.log('fetchLocations: No gbp_account_id, skipping');
      return;
    }

    console.log('fetchLocations: Fetching locations...');
    setLoadingLocations(true);
    try {
      const data = await googleBusinessApi.getLocations();
      console.log('fetchLocations: Received locations:', data);
      setLocations(data);
    } catch (error) {
      console.error('Failed to fetch GBP locations:', error);
      onMessage({ type: 'error', text: 'Failed to fetch business locations' });
    } finally {
      setLoadingLocations(false);
    }
  }, [profile?.gbp_account_id, onMessage]);

  // Fetch categories
  const fetchCategories = useCallback(async (search?: string) => {
    setLoadingCategories(true);
    try {
      const data = await googleBusinessApi.searchCategories(search);
      setCategories(data);
    } catch (error) {
      console.error('Failed to fetch categories:', error);
    } finally {
      setLoadingCategories(false);
    }
  }, []);

  useEffect(() => {
    if (profile?.status === 'connected') {
      fetchAccounts();
    }
  }, [profile?.status, fetchAccounts]);

  useEffect(() => {
    if (profile?.gbp_account_id) {
      fetchLocations();
    }
  }, [profile?.gbp_account_id, fetchLocations]);

  // Fetch all categories when form opens
  useEffect(() => {
    if (showCreateLocation && categories.length === 0) {
      fetchCategories();
    }
  }, [showCreateLocation, categories.length, fetchCategories]);

  // Handle connect
  const handleConnect = async () => {
    setConnecting(true);
    try {
      const data = await googleBusinessApi.connect();
      
      // Check if API is not configured (mock mode)
      if (data.is_mock_mode || data.requires_approval) {
        setShowApiNotConfigured(true);
        if (data.approval_url) {
          setApiApprovalUrl(data.approval_url);
        }
        setConnecting(false);
        return;
      }
      
      // Real mode - redirect to Google OAuth
      if (data.authorization_url) {
        window.location.href = data.authorization_url;
      }
    } catch (error) {
      console.error('Failed to connect:', error);
      onMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to connect' });
      setConnecting(false);
    }
  };

  // Handle test connect (mock mode)
  const handleTestConnect = async () => {
    setConnecting(true);
    try {
      const data = await googleBusinessApi.testConnect();
      setProfile(data.profile);
      onMessage({ type: 'success', text: `${data.message} (Mock Mode)` });
    } catch (error) {
      console.error('Failed to test connect:', error);
      onMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to connect' });
    } finally {
      setConnecting(false);
    }
  };

  // Handle disconnect
  const handleDisconnect = async () => {
    setConnecting(true);
    try {
      await googleBusinessApi.disconnect();
      setProfile(null);
      setAccounts([]);
      setLocations([]);
      onMessage({ type: 'success', text: 'Google Business Profile disconnected' });
    } catch (error) {
      console.error('Failed to disconnect:', error);
      onMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to disconnect' });
    } finally {
      setConnecting(false);
    }
  };

  // Handle account selection
  const handleSelectAccount = async (accountId: string) => {
    try {
      await googleBusinessApi.selectAccount(accountId);
      await fetchStatus();
      setShowAccountSelector(false);
      onMessage({ type: 'success', text: 'Business account selected' });
    } catch (error) {
      console.error('Failed to select account:', error);
      onMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to select account' });
    }
  };

  // Handle create location
  const handleCreateLocation = async () => {
    console.log('handleCreateLocation called with:', newLocation);
    
    // Validate all required fields
    const missingFields = [];
    if (!newLocation.business_name) missingFields.push('Business Name');
    if (!newLocation.primary_category) missingFields.push('Category');
    if (!newLocation.address_line1) missingFields.push('Address');
    if (!newLocation.city) missingFields.push('City');
    if (!newLocation.state) missingFields.push('State');
    if (!newLocation.postal_code) missingFields.push('Postal Code');
    
    if (missingFields.length > 0) {
      console.log('Missing fields:', missingFields);
      onMessage({ type: 'error', text: `Please fill in required fields: ${missingFields.join(', ')}` });
      return;
    }
    
    console.log('Validation passed, calling API...');

    try {
      await googleBusinessApi.createLocation(newLocation);
      await fetchLocations();
      setShowCreateLocation(false);
      setShowLocations(true); // Show locations list after creating
      setNewLocation({
        business_name: '',
        primary_category: '',
        address_line1: '',
        address_line2: '',
        city: '',
        state: '',
        postal_code: '',
        country: 'US',
        phone_number: '',
        website_url: '',
      });
      setShowCustomCategory(false);
      onMessage({ type: 'success', text: 'Business location created successfully!' });
    } catch (error) {
      console.error('Failed to create location:', error);
      onMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to create location' });
    }
  };

  // Handle delete location
  const handleDeleteLocation = async (id: number) => {
    if (!confirm('Are you sure you want to delete this location?')) return;

    try {
      await googleBusinessApi.deleteLocation(String(id));
      await fetchLocations();
      onMessage({ type: 'success', text: 'Location deleted successfully' });
    } catch (error) {
      console.error('Failed to delete location:', error);
      onMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to delete location' });
    }
  };

  const isConnected = profile?.status === 'connected';

  if (loading) {
    return (
      <div className="glass-card p-6">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 bg-white/10 rounded-xl animate-pulse" />
          <div className="flex-1">
            <div className="h-5 w-32 bg-white/10 rounded animate-pulse mb-2" />
            <div className="h-4 w-24 bg-white/10 rounded animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card p-6 hover:border-[#4285F4]/30 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div className="p-2 rounded-xl bg-white">
            {/* Google Business Profile Icon - Official storefront in location pin */}
            <svg className="w-10 h-10" viewBox="0 0 48 48" fill="none">
              {/* Location Pin - Google Blue */}
              <path d="M24 4C16.27 4 10 10.27 10 18c0 10.5 14 26 14 26s14-15.5 14-26c0-7.73-6.27-14-14-14z" fill="#4285F4"/>
              {/* Storefront Building - White */}
              <rect x="16" y="16" width="16" height="12" rx="1" fill="white"/>
              {/* Storefront Awning */}
              <path d="M15 16h18v3c0 1-1 2-2.25 2s-2.25-1-2.25-2c0 1-1 2-2.25 2s-2.25-1-2.25-2c0 1-1 2-2.25 2s-2.25-1-2.25-2c0 1-1 2-2.25 2S15 20 15 19v-3z" fill="white"/>
              {/* Door */}
              <rect x="21" y="22" width="6" height="6" rx="0.5" fill="#4285F4"/>
              {/* Door handle */}
              <circle cx="25.5" cy="25" r="0.75" fill="white"/>
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-heading font-semibold text-white">
              Google Business Profile
            </h3>
            {isConnected ? (
              <p className="text-sm text-brand-silver/70">
                {profile.google_email || profile.gbp_account_name || 'Connected'}
                {profile.is_mock && (
                  <span className="ml-2 text-xs text-yellow-400">(Mock Mode)</span>
                )}
              </p>
            ) : (
              <p className="text-sm text-brand-silver/70">
                Create and manage your business listings
              </p>
            )}
          </div>
        </div>
        {/* Status Indicator */}
        {isConnected && (
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-[#34A853] rounded-full animate-pulse" />
            <span className="text-xs text-[#34A853]">Connected</span>
          </div>
        )}
      </div>

      {/* Connection Actions */}
      {!isConnected ? (
        <div className="mt-4 space-y-4">
          {/* API Not Configured Message */}
          {showApiNotConfigured && (
            <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <svg className="w-6 h-6 text-yellow-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div className="flex-1">
                  <h4 className="text-yellow-400 font-semibold text-sm">Google Business Profile API Not Configured</h4>
                  <p className="text-brand-silver/80 text-sm mt-1">
                    The Google Business Profile API requires a verification and approval process from Google. 
                    This is a standard requirement for accessing business profile data.
                  </p>
                  {apiApprovalUrl && (
                    <a 
                      href={apiApprovalUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[#4285F4] hover:text-[#5a9bf6] text-sm mt-2"
                    >
                      Learn about the approval process
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  )}
                  <div className="mt-3 pt-3 border-t border-yellow-500/20">
                    <p className="text-brand-silver/60 text-xs mb-2">
                      In the meantime, you can use <strong>Test Mode</strong> to explore all features with simulated data.
                    </p>
                    <button
                      onClick={() => {
                        setShowApiNotConfigured(false);
                        handleTestConnect();
                      }}
                      disabled={connecting}
                      className="px-3 py-1.5 bg-white/10 text-white border border-white/20 rounded-lg 
                               hover:bg-white/20 transition-colors disabled:opacity-50 text-sm flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                      Use Test Mode Instead
                    </button>
                  </div>
                </div>
                <button
                  onClick={() => setShowApiNotConfigured(false)}
                  className="text-brand-silver/50 hover:text-white transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
          <button
            onClick={handleConnect}
            disabled={connecting}
            className="px-4 py-2 bg-[#4285F4] text-white font-semibold rounded-lg 
                     hover:bg-[#3367D6] transition-colors disabled:opacity-50 flex items-center gap-2 shadow-md"
          >
            {connecting ? (
              <>
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Connecting...
              </>
            ) : (
              <>
                {/* Google "G" Icon */}
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path fill="#fff" d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.748L12.545,10.239z"/>
                </svg>
                Connect with Google
              </>
            )}
          </button>
          <button
            onClick={handleTestConnect}
            disabled={connecting}
            className="px-4 py-2 bg-white/10 text-white border border-white/20 rounded-lg hover:bg-white/20 
                     transition-colors disabled:opacity-50 text-sm"
          >
            Test Mode
          </button>
          </div>
        </div>
      ) : (
        <>
          {/* Account Selector */}
          {!profile.gbp_account_id && (
            <div className="mt-4">
              <button
                onClick={() => {
                  setShowAccountSelector(!showAccountSelector);
                  if (!showAccountSelector && accounts.length === 0) {
                    fetchAccounts();
                  }
                }}
                className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg 
                         hover:bg-white/10 transition-colors text-left flex items-center justify-between"
              >
                <span className="text-white">Select a Business Account</span>
                <svg 
                  className={`w-5 h-5 text-brand-silver transition-transform ${showAccountSelector ? 'rotate-180' : ''}`}
                  fill="none" 
                  viewBox="0 0 24 24" 
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {showAccountSelector && (
                <div className="mt-2 bg-white/5 rounded-lg p-3 space-y-2 max-h-48 overflow-y-auto">
                  {loadingAccounts ? (
                    <div className="text-center py-4">
                      <svg className="w-6 h-6 animate-spin mx-auto text-brand-electric" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      <p className="text-sm text-brand-silver/50 mt-2">Loading accounts...</p>
                    </div>
                  ) : accounts.length > 0 ? (
                    accounts.map((account) => (
                      <button
                        key={account.name}
                        onClick={() => handleSelectAccount(account.name)}
                        className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-white/10 transition-colors"
                      >
                        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-green-500 flex items-center justify-center">
                          <span className="text-white font-bold">
                            {account.accountName.charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <div className="text-left flex-1">
                          <p className="text-white font-medium">{account.accountName}</p>
                          <p className="text-xs text-brand-silver/70">
                            {account.type} • {account.role}
                          </p>
                        </div>
                      </button>
                    ))
                  ) : (
                    <p className="text-center text-brand-silver/50 py-4">No accounts found</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Locations Section */}
          {profile.gbp_account_id && (
            <div className="mt-4 space-y-3">
              {/* Action Buttons */}
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setShowLocations(!showLocations)}
                  className="px-3 py-2 bg-[#4285F4]/20 text-[#4285F4] border border-[#4285F4]/30 rounded-lg hover:bg-[#4285F4]/30 
                           transition-colors text-sm flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                          d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                          d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {showLocations ? 'Hide' : 'View'} Locations ({locations.length})
                </button>
                <button
                  onClick={() => setShowCreateLocation(!showCreateLocation)}
                  className="px-3 py-2 bg-[#34A853] text-white font-semibold rounded-lg hover:bg-[#2E9549] 
                           transition-colors text-sm flex items-center gap-2 shadow-sm"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add Location
                </button>
                <button
                  onClick={handleDisconnect}
                  disabled={connecting}
                  className="px-3 py-2 bg-[#EA4335]/20 text-[#EA4335] border border-[#EA4335]/30 rounded-lg hover:bg-[#EA4335]/30 
                           transition-colors text-sm disabled:opacity-50"
                >
                  Disconnect
                </button>
              </div>

              {/* Locations List */}
              {showLocations && (
                <div className="bg-white/5 rounded-lg p-4 space-y-3 max-h-64 overflow-y-auto">
                  {loadingLocations ? (
                    <div className="text-center py-4">
                      <svg className="w-6 h-6 animate-spin mx-auto text-[#4285F4]" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                    </div>
                  ) : locations.length > 0 ? (
                    locations.map((location) => (
                      <div
                        key={location.location_id}
                        className="flex items-start justify-between p-3 bg-white/5 rounded-lg"
                      >
                        <div className="flex-1">
                          <p className="text-white font-medium">{location.business_name}</p>
                          <p className="text-sm text-brand-silver/70">{location.full_address}</p>
                          {location.primary_category && (
                            <span className="inline-block mt-1 px-2 py-0.5 bg-[#4285F4]/20 
                                           text-[#4285F4] text-xs rounded">
                              {location.primary_category}
                            </span>
                          )}
                          <div className="flex items-center gap-2 mt-2">
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              location.verification_status === 'verified'
                                ? 'bg-[#34A853]/20 text-[#34A853]'
                                : location.verification_status === 'pending'
                                  ? 'bg-[#FBBC05]/20 text-[#FBBC05]'
                                  : 'bg-gray-500/20 text-gray-400'
                            }`}>
                              {location.verification_status}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={() => handleDeleteLocation(location.id)}
                          className="p-2 text-[#EA4335] hover:bg-[#EA4335]/20 rounded-lg transition-colors"
                          title="Delete location"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    ))
                  ) : (
                    <p className="text-center text-brand-silver/50 py-4">
                      No locations yet. Add your first business location!
                    </p>
                  )}
                </div>
              )}

              {/* Create Location Form */}
              {showCreateLocation && (
                <div className="bg-white/5 rounded-lg p-4 space-y-4">
                  <h4 className="text-white font-medium">Add New Business Location</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Business Name */}
                    <div className="md:col-span-2">
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        Business Name *
                      </label>
                      <input
                        type="text"
                        value={newLocation.business_name}
                        onChange={(e) => setNewLocation({ ...newLocation, business_name: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="My Business Name"
                      />
                    </div>

                    {/* Category */}
                    <div className="md:col-span-2">
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        Business Category *
                      </label>
                      {loadingCategories ? (
                        <div className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-brand-silver/50">
                          Loading categories...
                        </div>
                      ) : showCustomCategory ? (
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={newLocation.primary_category}
                            onChange={(e) => setNewLocation({ ...newLocation, primary_category: e.target.value })}
                            className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                     text-white focus:border-[#4285F4] focus:outline-none"
                            placeholder="Enter custom category..."
                            autoFocus
                          />
                          <button
                            type="button"
                            onClick={() => {
                              setShowCustomCategory(false);
                              setNewLocation({ ...newLocation, primary_category: '' });
                            }}
                            className="px-3 py-2 bg-white/10 text-white border border-white/20 rounded-lg hover:bg-white/20 text-sm"
                          >
                            Back
                          </button>
                        </div>
                      ) : (
                        <select
                          value={newLocation.primary_category}
                          onChange={(e) => {
                            if (e.target.value === '__OTHER__') {
                              setShowCustomCategory(true);
                              setNewLocation({ ...newLocation, primary_category: '' });
                            } else {
                              setNewLocation({ ...newLocation, primary_category: e.target.value });
                            }
                          }}
                          className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                   text-white focus:border-brand-electric focus:outline-none
                                   [&>option]:bg-gray-800 [&>option]:text-white"
                        >
                          <option value="">-- Select a category --</option>
                          {categories.map((cat) => (
                            <option key={cat.name} value={cat.displayName}>
                              {cat.displayName}
                            </option>
                          ))}
                          <option value="__OTHER__">Other (enter custom category)</option>
                        </select>
                      )}
                    </div>

                    {/* Address */}
                    <div className="md:col-span-2">
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        Address Line 1 *
                      </label>
                      <input
                        type="text"
                        value={newLocation.address_line1}
                        onChange={(e) => setNewLocation({ ...newLocation, address_line1: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="123 Main Street"
                      />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        Address Line 2
                      </label>
                      <input
                        type="text"
                        value={newLocation.address_line2}
                        onChange={(e) => setNewLocation({ ...newLocation, address_line2: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="Suite 100"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        City *
                      </label>
                      <input
                        type="text"
                        value={newLocation.city}
                        onChange={(e) => setNewLocation({ ...newLocation, city: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="San Francisco"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        State
                      </label>
                      <input
                        type="text"
                        value={newLocation.state}
                        onChange={(e) => setNewLocation({ ...newLocation, state: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="CA"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        Postal Code
                      </label>
                      <input
                        type="text"
                        value={newLocation.postal_code}
                        onChange={(e) => setNewLocation({ ...newLocation, postal_code: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="94102"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        Country
                      </label>
                      <input
                        type="text"
                        value={newLocation.country}
                        onChange={(e) => setNewLocation({ ...newLocation, country: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="US"
                        maxLength={2}
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        Phone Number
                      </label>
                      <input
                        type="tel"
                        value={newLocation.phone_number}
                        onChange={(e) => setNewLocation({ ...newLocation, phone_number: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="+1-555-555-5555"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-brand-silver/70 mb-1">
                        Website URL
                      </label>
                      <input
                        type="url"
                        value={newLocation.website_url}
                        onChange={(e) => setNewLocation({ ...newLocation, website_url: e.target.value })}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="https://example.com"
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      onClick={() => {
                        setShowCreateLocation(false);
                        setShowCustomCategory(false);
                      }}
                      className="px-4 py-2 bg-white/10 text-white border border-white/20 rounded-lg hover:bg-white/20 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleCreateLocation}
                      className="px-4 py-2 bg-[#4285F4] text-white font-semibold rounded-lg hover:bg-[#3367D6] transition-colors shadow-sm"
                    >
                      Create Location
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Not connected - Feature highlights */}
      {!isConnected && (
        <div className="mt-4 p-4 bg-white/5 rounded-lg">
          <p className="text-sm text-brand-silver/70 mb-3">
            Connect to Google Business Profile to:
          </p>
          <ul className="space-y-2 text-sm text-brand-silver/80">
            <li className="flex items-center gap-2">
              <svg className="w-4 h-4 text-brand-mint" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Create and manage business listings
            </li>
            <li className="flex items-center gap-2">
              <svg className="w-4 h-4 text-brand-mint" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Update business information
            </li>
            <li className="flex items-center gap-2">
              <svg className="w-4 h-4 text-brand-mint" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Manage multiple locations
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}
