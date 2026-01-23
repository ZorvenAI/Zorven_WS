'use client';

import { useState, useEffect, useCallback } from 'react';
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
  const [categorySearch, setCategorySearch] = useState('');

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
    if (!profile?.gbp_account_id) return;

    setLoadingLocations(true);
    try {
      const data = await googleBusinessApi.getLocations();
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

  // Debounced category search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (showCreateLocation) {
        fetchCategories(categorySearch || undefined);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [categorySearch, showCreateLocation, fetchCategories]);

  // Handle connect
  const handleConnect = async () => {
    setConnecting(true);
    try {
      const data = await googleBusinessApi.connect();
      window.location.href = data.authorization_url;
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
    if (!newLocation.business_name || !newLocation.address_line1 || !newLocation.city) {
      onMessage({ type: 'error', text: 'Please fill in required fields (Business Name, Address, City)' });
      return;
    }

    try {
      await googleBusinessApi.createLocation(newLocation);
      await fetchLocations();
      setShowCreateLocation(false);
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
      onMessage({ type: 'success', text: 'Business location created successfully!' });
    } catch (error) {
      console.error('Failed to create location:', error);
      onMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to create location' });
    }
  };

  // Handle delete location
  const handleDeleteLocation = async (locationId: string) => {
    if (!confirm('Are you sure you want to delete this location?')) return;

    try {
      await googleBusinessApi.deleteLocation(locationId);
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
    <div className="glass-card p-6 hover:border-brand-electric/30 transition-all">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div className="p-3 rounded-xl bg-gradient-to-br from-blue-500 via-green-500 to-yellow-500 text-white">
            {/* Google Business Profile Icon */}
            <svg className="w-8 h-8" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22 12c0-5.52-4.48-10-10-10S2 6.48 2 12s4.48 10 10 10 10-4.48 10-10zm-10-2c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0-6c3.31 0 6 2.69 6 6 0 1.66-.67 3.16-1.76 4.24l-1.42-1.42A3.93 3.93 0 0016 10c0-2.21-1.79-4-4-4S8 7.79 8 10c0 .9.3 1.73.82 2.4L7.4 13.82A5.96 5.96 0 016 10c0-3.31 2.69-6 6-6z"/>
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
            <span className="w-2 h-2 bg-brand-mint rounded-full animate-pulse" />
            <span className="text-xs text-brand-mint">Connected</span>
          </div>
        )}
      </div>

      {/* Connection Actions */}
      {!isConnected ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={handleConnect}
            disabled={connecting}
            className="px-4 py-2 bg-gradient-to-r from-blue-500 to-green-500 text-white rounded-lg 
                     hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
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
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.748L12.545,10.239z"/>
                </svg>
                Connect with Google
              </>
            )}
          </button>
          <button
            onClick={handleTestConnect}
            disabled={connecting}
            className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 
                     transition-colors disabled:opacity-50 text-sm"
          >
            Test Mode
          </button>
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
                  className="px-3 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 
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
                  className="px-3 py-2 bg-brand-electric text-white rounded-lg hover:bg-brand-electric/80 
                           transition-colors text-sm flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add Location
                </button>
                <button
                  onClick={handleDisconnect}
                  disabled={connecting}
                  className="px-3 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 
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
                      <svg className="w-6 h-6 animate-spin mx-auto text-brand-electric" viewBox="0 0 24 24" fill="none">
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
                            <span className="inline-block mt-1 px-2 py-0.5 bg-brand-electric/20 
                                           text-brand-electric text-xs rounded">
                              {location.primary_category}
                            </span>
                          )}
                          <div className="flex items-center gap-2 mt-2">
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              location.verification_status === 'verified'
                                ? 'bg-green-500/20 text-green-400'
                                : location.verification_status === 'pending'
                                  ? 'bg-yellow-500/20 text-yellow-400'
                                  : 'bg-gray-500/20 text-gray-400'
                            }`}>
                              {location.verification_status}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={() => handleDeleteLocation(location.location_id)}
                          className="p-2 text-red-400 hover:bg-red-500/20 rounded-lg transition-colors"
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
                        Business Category
                      </label>
                      <input
                        type="text"
                        value={categorySearch}
                        onChange={(e) => setCategorySearch(e.target.value)}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg 
                                 text-white focus:border-brand-electric focus:outline-none"
                        placeholder="Search categories..."
                      />
                      {categories.length > 0 && categorySearch && (
                        <div className="mt-2 bg-white/5 rounded-lg max-h-32 overflow-y-auto">
                          {loadingCategories ? (
                            <div className="p-3 text-center text-brand-silver/50">Loading...</div>
                          ) : (
                            categories.slice(0, 5).map((cat) => (
                              <button
                                key={cat.name}
                                onClick={() => {
                                  setNewLocation({ ...newLocation, primary_category: cat.displayName });
                                  setCategorySearch(cat.displayName);
                                  setCategories([]);
                                }}
                                className="w-full px-3 py-2 text-left text-sm text-white hover:bg-white/10"
                              >
                                {cat.displayName}
                              </button>
                            ))
                          )}
                        </div>
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
                      onClick={() => setShowCreateLocation(false)}
                      className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleCreateLocation}
                      className="px-4 py-2 bg-brand-electric text-white rounded-lg hover:bg-brand-electric/80 transition-colors"
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
