'use client';

import { useState, useCallback, useEffect } from 'react';
import { apiClient } from '@/lib/api';

// Types
interface TwitterAnalyticsData {
  user?: {
    username?: string;
    name?: string;
    profile_image_url?: string;
    metrics?: {
      followers: number;
      following: number;
      tweets: number;
      listed: number;
    };
  };
  tweets?: Array<{
    tweet_id: string;
    text: string;
    created_at: string;
    metrics: {
      impressions: number;
      likes: number;
      retweets: number;
      replies: number;
      quotes: number;
      bookmarks: number;
    };
  }>;
  totals?: {
    total_impressions: number;
    total_likes: number;
    total_retweets: number;
    total_replies: number;
    total_quotes: number;
    total_bookmarks: number;
    engagement_rate: number;
  };
  test_mode?: boolean;
  rate_limited?: boolean;
  rate_limit_message?: string;
}

interface LinkedInAnalyticsData {
  profile?: {
    name?: string;
    email?: string;
    picture?: string;
  };
  network?: {
    connections: number;
  };
  posts?: Array<{
    post_urn: string;
    text: string;
    created_time: number;
    metrics: {
      likes: number;
      comments: number;
      shares: number;
      impressions: number;
    };
  }>;
  totals?: {
    total_posts: number;
    total_likes: number;
    total_comments: number;
    engagement_rate: number;
  };
  test_mode?: boolean;
}

interface FacebookAnalyticsData {
  page_id?: string;
  page_name?: string;
  insights?: {
    page_impressions?: number;
    page_engaged_users?: number;
    page_fans?: number;
    page_fan_adds?: number;
    page_post_engagements?: number;
    page_views_total?: number;
  };
  recent_posts?: Array<{
    id: string;
    message: string;
    created_time: string;
    permalink_url?: string;
    full_picture?: string;
    likes: number;
    comments: number;
    shares: number;
  }>;
  test_mode?: boolean;
}

interface InstagramAnalyticsData {
  account_id?: string;
  username?: string;
  profile_picture_url?: string;
  insights?: {
    follower_count?: number;
    follows_count?: number;
    media_count?: number;
    impressions?: number;
    reach?: number;
    profile_views?: number;
    website_clicks?: number;
  };
  recent_media?: Array<{
    id: string;
    caption?: string;
    media_type: string;
    permalink: string;
    thumbnail_url?: string;
    timestamp: string;
    like_count: number;
    comments_count: number;
  }>;
  test_mode?: boolean;
}

interface WebhookEvent {
  id: number;
  event_type: string;
  created_at: string;
  resource_urn?: string;
  payload: Record<string, unknown>;
  read: boolean;
}

interface SocialProfiles {
  twitter?: { connected: boolean };
  linkedin?: { connected: boolean };
  facebook?: { connected: boolean };
  instagram?: { connected: boolean };
}

export default function SocialAnalytics() {
  // Profile connection status
  const [profiles, setProfiles] = useState<SocialProfiles | null>(null);
  const [loadingProfiles, setLoadingProfiles] = useState(true);

  // Twitter Analytics state
  const [showTwitterAnalytics, setShowTwitterAnalytics] = useState(true);
  const [twitterAnalyticsLoading, setTwitterAnalyticsLoading] = useState(false);
  const [twitterAnalyticsData, setTwitterAnalyticsData] = useState<TwitterAnalyticsData | null>(null);

  // Twitter Webhook notifications state
  const [twitterWebhookEvents, setTwitterWebhookEvents] = useState<WebhookEvent[]>([]);
  const [twitterUnreadCount, setTwitterUnreadCount] = useState(0);
  const [showTwitterNotifications, setShowTwitterNotifications] = useState(false);

  // LinkedIn Analytics state
  const [showLinkedInAnalytics, setShowLinkedInAnalytics] = useState(true);
  const [linkedInAnalyticsLoading, setLinkedInAnalyticsLoading] = useState(false);
  const [linkedInAnalyticsData, setLinkedInAnalyticsData] = useState<LinkedInAnalyticsData | null>(null);

  // LinkedIn Webhook notifications state
  const [linkedInWebhookEvents, setLinkedInWebhookEvents] = useState<WebhookEvent[]>([]);
  const [linkedInUnreadCount, setLinkedInUnreadCount] = useState(0);
  const [showLinkedInNotifications, setShowLinkedInNotifications] = useState(false);

  // Facebook Analytics state
  const [showFacebookAnalytics, setShowFacebookAnalytics] = useState(true);
  const [facebookAnalyticsLoading, setFacebookAnalyticsLoading] = useState(false);
  const [facebookAnalyticsData, setFacebookAnalyticsData] = useState<FacebookAnalyticsData | null>(null);

  // Facebook Webhook notifications state
  const [facebookWebhookEvents, setFacebookWebhookEvents] = useState<WebhookEvent[]>([]);
  const [facebookUnreadCount, setFacebookUnreadCount] = useState(0);
  const [showFacebookNotifications, setShowFacebookNotifications] = useState(false);

  // Instagram Analytics state
  const [showInstagramAnalytics, setShowInstagramAnalytics] = useState(true);
  const [instagramAnalyticsLoading, setInstagramAnalyticsLoading] = useState(false);
  const [instagramAnalyticsData, setInstagramAnalyticsData] = useState<InstagramAnalyticsData | null>(null);

  // Instagram Webhook notifications state
  const [instagramWebhookEvents, setInstagramWebhookEvents] = useState<WebhookEvent[]>([]);
  const [instagramUnreadCount, setInstagramUnreadCount] = useState(0);
  const [showInstagramNotifications, setShowInstagramNotifications] = useState(false);

  // Fetch profile status
  const fetchProfiles = useCallback(async () => {
    try {
      const response = await apiClient.get('/automation/social-profiles/status/');
      if (response.ok) {
        const data = await response.json();
        setProfiles(data);
      }
    } catch (error) {
      console.error('Failed to fetch profiles:', error);
    } finally {
      setLoadingProfiles(false);
    }
  }, []);

  // Fetch Twitter analytics
  const fetchTwitterAnalytics = useCallback(async () => {
    if (!profiles?.twitter?.connected) return;
    
    setTwitterAnalyticsLoading(true);
    try {
      const response = await apiClient.get('/automation/twitter/analytics/');
      if (response.ok) {
        const data = await response.json();
        setTwitterAnalyticsData(data);
      }
    } catch (error) {
      console.error('Failed to fetch Twitter analytics:', error);
    } finally {
      setTwitterAnalyticsLoading(false);
    }
  }, [profiles?.twitter?.connected]);

  // Fetch Twitter webhook events
  const fetchTwitterWebhookEvents = useCallback(async () => {
    if (!profiles?.twitter?.connected) return;
    
    try {
      const response = await apiClient.get('/automation/twitter/webhooks/events/?limit=20');
      if (response.ok) {
        const data = await response.json();
        setTwitterWebhookEvents(data.events || []);
        setTwitterUnreadCount(data.unread_count || 0);
      }
    } catch (error) {
      console.error('Failed to fetch Twitter webhook events:', error);
    }
  }, [profiles?.twitter?.connected]);

  // Mark Twitter events as read
  const markTwitterEventsAsRead = async (eventIds: number[]) => {
    try {
      const response = await apiClient.post('/automation/twitter/webhooks/events/', {
        event_ids: eventIds,
      });
      if (response.ok) {
        setTwitterWebhookEvents(prev => 
          prev.map(e => eventIds.includes(e.id) ? { ...e, read: true } : e)
        );
        setTwitterUnreadCount(prev => Math.max(0, prev - eventIds.length));
      }
    } catch (error) {
      console.error('Failed to mark Twitter events as read:', error);
    }
  };

  // Fetch LinkedIn analytics
  const fetchLinkedInAnalytics = useCallback(async () => {
    if (!profiles?.linkedin?.connected) return;
    
    setLinkedInAnalyticsLoading(true);
    try {
      const response = await apiClient.get('/automation/linkedin/analytics/');
      if (response.ok) {
        const data = await response.json();
        setLinkedInAnalyticsData(data);
      }
    } catch (error) {
      console.error('Failed to fetch LinkedIn analytics:', error);
    } finally {
      setLinkedInAnalyticsLoading(false);
    }
  }, [profiles?.linkedin?.connected]);

  // Fetch LinkedIn webhook events
  const fetchLinkedInWebhookEvents = useCallback(async () => {
    if (!profiles?.linkedin?.connected) return;
    
    try {
      const response = await apiClient.get('/automation/linkedin/webhooks/events/?limit=20');
      if (response.ok) {
        const data = await response.json();
        setLinkedInWebhookEvents(data.events || []);
        setLinkedInUnreadCount(data.unread_count || 0);
      }
    } catch (error) {
      console.error('Failed to fetch LinkedIn webhook events:', error);
    }
  }, [profiles?.linkedin?.connected]);

  // Mark LinkedIn events as read
  const markLinkedInEventsAsRead = async (eventIds: number[]) => {
    try {
      const response = await apiClient.post('/automation/linkedin/webhooks/events/', {
        event_ids: eventIds,
      });
      if (response.ok) {
        setLinkedInWebhookEvents(prev => 
          prev.map(e => eventIds.includes(e.id) ? { ...e, read: true } : e)
        );
        setLinkedInUnreadCount(prev => Math.max(0, prev - eventIds.length));
      }
    } catch (error) {
      console.error('Failed to mark LinkedIn events as read:', error);
    }
  };

  // Fetch Facebook analytics
  const fetchFacebookAnalytics = useCallback(async () => {
    if (!profiles?.facebook?.connected) return;
    
    setFacebookAnalyticsLoading(true);
    try {
      const response = await apiClient.get('/automation/facebook/analytics/');
      if (response.ok) {
        const data = await response.json();
        setFacebookAnalyticsData(data);
      }
    } catch (error) {
      console.error('Failed to fetch Facebook analytics:', error);
    } finally {
      setFacebookAnalyticsLoading(false);
    }
  }, [profiles?.facebook?.connected]);

  // Fetch Facebook webhook events
  const fetchFacebookWebhookEvents = useCallback(async () => {
    if (!profiles?.facebook?.connected) return;
    
    try {
      const response = await apiClient.get('/automation/facebook/webhooks/events/?limit=20');
      if (response.ok) {
        const data = await response.json();
        setFacebookWebhookEvents(data.events || []);
        setFacebookUnreadCount(data.unread_count || 0);
      }
    } catch (error) {
      console.error('Failed to fetch Facebook webhook events:', error);
    }
  }, [profiles?.facebook?.connected]);

  // Mark Facebook events as read
  const markFacebookEventsAsRead = async (eventIds: number[]) => {
    try {
      const response = await apiClient.post('/automation/facebook/webhooks/events/', {
        event_ids: eventIds,
      });
      if (response.ok) {
        setFacebookWebhookEvents(prev => 
          prev.map(e => eventIds.includes(e.id) ? { ...e, read: true } : e)
        );
        setFacebookUnreadCount(prev => Math.max(0, prev - eventIds.length));
      }
    } catch (error) {
      console.error('Failed to mark Facebook events as read:', error);
    }
  };

  // Fetch Instagram analytics
  const fetchInstagramAnalytics = useCallback(async () => {
    if (!profiles?.instagram?.connected) return;
    
    setInstagramAnalyticsLoading(true);
    try {
      const response = await apiClient.get('/automation/instagram/analytics/');
      if (response.ok) {
        const data = await response.json();
        setInstagramAnalyticsData(data);
      }
    } catch (error) {
      console.error('Failed to fetch Instagram analytics:', error);
    } finally {
      setInstagramAnalyticsLoading(false);
    }
  }, [profiles?.instagram?.connected]);

  // Fetch Instagram webhook events
  const fetchInstagramWebhookEvents = useCallback(async () => {
    if (!profiles?.instagram?.connected) return;
    
    try {
      const response = await apiClient.get('/automation/instagram/webhooks/events/?limit=20');
      if (response.ok) {
        const data = await response.json();
        setInstagramWebhookEvents(data.events || []);
        setInstagramUnreadCount(data.unread_count || 0);
      }
    } catch (error) {
      console.error('Failed to fetch Instagram webhook events:', error);
    }
  }, [profiles?.instagram?.connected]);

  // Mark Instagram events as read
  const markInstagramEventsAsRead = async (eventIds: number[]) => {
    try {
      const response = await apiClient.post('/automation/instagram/webhooks/events/', {
        event_ids: eventIds,
      });
      if (response.ok) {
        setInstagramWebhookEvents(prev => 
          prev.map(e => eventIds.includes(e.id) ? { ...e, read: true } : e)
        );
        setInstagramUnreadCount(prev => Math.max(0, prev - eventIds.length));
      }
    } catch (error) {
      console.error('Failed to mark Instagram events as read:', error);
    }
  };

  // Initial data fetch
  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  // Fetch analytics when profiles are loaded
  useEffect(() => {
    if (profiles?.twitter?.connected) {
      fetchTwitterAnalytics();
    }
    if (profiles?.linkedin?.connected) {
      fetchLinkedInAnalytics();
    }
    if (profiles?.facebook?.connected) {
      fetchFacebookAnalytics();
    }
    if (profiles?.instagram?.connected) {
      fetchInstagramAnalytics();
    }
  }, [profiles, fetchTwitterAnalytics, fetchLinkedInAnalytics, fetchFacebookAnalytics, fetchInstagramAnalytics]);

  if (loadingProfiles) {
    return (
      <div className="glass-card p-6">
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric"></div>
        </div>
      </div>
    );
  }

  const hasConnectedPlatforms = profiles?.twitter?.connected || profiles?.linkedin?.connected || profiles?.facebook?.connected || profiles?.instagram?.connected;

  if (!hasConnectedPlatforms) {
    return (
      <div className="glass-card p-6">
        <h2 className="text-xl font-heading font-bold text-white mb-4">Social Analytics</h2>
        <div className="text-center py-8 text-brand-silver/70">
          <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <p>Connect your social accounts to see analytics</p>
          <a href="/automation" className="text-brand-electric hover:underline mt-2 inline-block">
            Go to Automation →
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Twitter Analytics */}
      {profiles?.twitter?.connected && (
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-heading font-bold text-white flex items-center gap-2">
              <svg className="w-5 h-5 text-brand-electric" fill="currentColor" viewBox="0 0 24 24">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
              </svg>
              Twitter Analytics
            </h2>
            <div className="flex items-center gap-2">
              {/* Notifications Bell */}
              <div className="relative">
                <button
                  onClick={() => {
                    setShowTwitterNotifications(!showTwitterNotifications);
                    if (!showTwitterNotifications) fetchTwitterWebhookEvents();
                  }}
                  className="p-2 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 transition-colors relative"
                  title="Notifications"
                >
                  <svg className="w-5 h-5 text-brand-silver" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                  </svg>
                  {twitterUnreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                      {twitterUnreadCount > 9 ? '9+' : twitterUnreadCount}
                    </span>
                  )}
                </button>
                
                {/* Notifications Dropdown */}
                {showTwitterNotifications && (
                  <div className="absolute right-0 top-12 w-80 bg-brand-midnight border border-brand-ghost/30 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
                    <div className="p-3 border-b border-brand-ghost/30 flex items-center justify-between">
                      <span className="font-medium text-white">Notifications</span>
                      {twitterWebhookEvents.length > 0 && (
                        <button
                          onClick={() => markTwitterEventsAsRead(twitterWebhookEvents.map(e => e.id))}
                          className="text-xs text-brand-electric hover:underline"
                        >
                          Mark all read
                        </button>
                      )}
                    </div>
                    {twitterWebhookEvents.length === 0 ? (
                      <div className="p-4 text-center text-brand-silver/70">
                        <p>No notifications yet</p>
                        <p className="text-xs mt-1">Webhook events will appear here</p>
                      </div>
                    ) : (
                      <div className="divide-y divide-brand-ghost/20">
                        {twitterWebhookEvents.map(event => (
                          <div 
                            key={event.id}
                            className={`p-3 ${!event.read ? 'bg-brand-electric/5' : ''} hover:bg-brand-ghost/10 cursor-pointer`}
                            onClick={() => !event.read && markTwitterEventsAsRead([event.id])}
                          >
                            <div className="flex items-start gap-2">
                              <span className={`w-2 h-2 rounded-full mt-2 ${!event.read ? 'bg-brand-electric' : 'bg-transparent'}`} />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-white">
                                  {event.event_type === 'favorite' && '❤️ Someone liked your tweet'}
                                  {event.event_type === 'follow' && '👤 New follower'}
                                  {event.event_type === 'retweet' && '🔄 Someone retweeted'}
                                  {event.event_type === 'mention' && '💬 You were mentioned'}
                                  {event.event_type === 'direct_message' && '✉️ New direct message'}
                                  {event.event_type === 'tweet_create' && '🐦 New tweet activity'}
                                </p>
                                <p className="text-xs text-brand-silver/70">
                                  {new Date(event.created_at).toLocaleString()}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
              
              <button
                onClick={() => setShowTwitterAnalytics(!showTwitterAnalytics)}
                className="px-3 py-1.5 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 text-brand-silver transition-colors flex items-center gap-2 text-sm"
              >
                {showTwitterAnalytics ? 'Hide' : 'Show'}
                <svg className={`w-4 h-4 transition-transform ${showTwitterAnalytics ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <button
                onClick={fetchTwitterAnalytics}
                disabled={twitterAnalyticsLoading}
                className="p-2 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 transition-colors disabled:opacity-50"
                title="Refresh analytics"
              >
                <svg className={`w-4 h-4 text-brand-silver ${twitterAnalyticsLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          </div>

          {showTwitterAnalytics && (
            <>
              {twitterAnalyticsLoading && !twitterAnalyticsData ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-electric"></div>
                </div>
              ) : twitterAnalyticsData ? (
                <div>
                  {twitterAnalyticsData.test_mode && (
                    <div className="mb-4 px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-400 text-sm">
                      🧪 Test Mode - Showing simulated analytics data
                    </div>
                  )}
                  
                  {twitterAnalyticsData.rate_limited && (
                    <div className="mb-4 px-3 py-2 bg-orange-500/10 border border-orange-500/30 rounded-lg text-orange-400 text-sm">
                      ⚠️ {twitterAnalyticsData.rate_limit_message || 'Twitter API rate limit reached. Please try again in a few minutes.'}
                    </div>
                  )}
                  
                  {/* User Profile Stats */}
                  {twitterAnalyticsData.user && (
                    <div className="mb-4">
                      <div className="flex items-center gap-2 mb-3">
                        {twitterAnalyticsData.user.profile_image_url && (
                          <img src={twitterAnalyticsData.user.profile_image_url} alt="" className="w-8 h-8 rounded-full" />
                        )}
                        <span className="text-sm text-white">@{twitterAnalyticsData.user.username || 'Account'}</span>
                      </div>
                      <div className="grid grid-cols-4 gap-3">
                        <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                          <div className="text-lg font-bold text-brand-electric">{twitterAnalyticsData.user.metrics?.followers?.toLocaleString() || 0}</div>
                          <div className="text-xs text-brand-silver/70">Followers</div>
                        </div>
                        <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                          <div className="text-lg font-bold text-white">{twitterAnalyticsData.user.metrics?.following?.toLocaleString() || 0}</div>
                          <div className="text-xs text-brand-silver/70">Following</div>
                        </div>
                        <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                          <div className="text-lg font-bold text-white">{twitterAnalyticsData.user.metrics?.tweets?.toLocaleString() || 0}</div>
                          <div className="text-xs text-brand-silver/70">Tweets</div>
                        </div>
                        <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                          <div className="text-lg font-bold text-white">{twitterAnalyticsData.user.metrics?.listed?.toLocaleString() || 0}</div>
                          <div className="text-xs text-brand-silver/70">Listed</div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Engagement Summary */}
                  {twitterAnalyticsData.totals && (
                    <div className="grid grid-cols-4 gap-2">
                      <div className="bg-gradient-to-br from-blue-500/20 to-blue-600/10 rounded-lg p-3 text-center border border-blue-500/20">
                        <div className="text-lg font-bold text-blue-400">{twitterAnalyticsData.totals.total_impressions.toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Impressions</div>
                      </div>
                      <div className="bg-gradient-to-br from-red-500/20 to-red-600/10 rounded-lg p-3 text-center border border-red-500/20">
                        <div className="text-lg font-bold text-red-400">{twitterAnalyticsData.totals.total_likes.toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Likes</div>
                      </div>
                      <div className="bg-gradient-to-br from-green-500/20 to-green-600/10 rounded-lg p-3 text-center border border-green-500/20">
                        <div className="text-lg font-bold text-green-400">{twitterAnalyticsData.totals.total_retweets.toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Retweets</div>
                      </div>
                      <div className="bg-gradient-to-br from-brand-electric/20 to-brand-electric/10 rounded-lg p-3 text-center border border-brand-electric/20">
                        <div className="text-lg font-bold text-brand-electric">{twitterAnalyticsData.totals.engagement_rate}%</div>
                        <div className="text-xs text-brand-silver/70">Engagement</div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-4 text-brand-silver/70">
                  <p>Failed to load analytics.</p>
                  <button onClick={fetchTwitterAnalytics} className="text-brand-electric hover:underline mt-1 text-sm">
                    Try again
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* LinkedIn Analytics */}
      {profiles?.linkedin?.connected && (
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-heading font-bold text-white flex items-center gap-2">
              <svg className="w-5 h-5 text-[#0A66C2]" fill="currentColor" viewBox="0 0 24 24">
                <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
              </svg>
              LinkedIn Analytics
            </h2>
            <div className="flex items-center gap-2">
              {/* Notifications Bell */}
              <div className="relative">
                <button
                  onClick={() => {
                    setShowLinkedInNotifications(!showLinkedInNotifications);
                    if (!showLinkedInNotifications) fetchLinkedInWebhookEvents();
                  }}
                  className="p-2 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 transition-colors relative"
                  title="LinkedIn Notifications"
                >
                  <svg className="w-5 h-5 text-brand-silver" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                  </svg>
                  {linkedInUnreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                      {linkedInUnreadCount > 9 ? '9+' : linkedInUnreadCount}
                    </span>
                  )}
                </button>
                
                {/* Notifications Dropdown */}
                {showLinkedInNotifications && (
                  <div className="absolute right-0 top-12 w-80 bg-brand-midnight border border-brand-ghost/30 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
                    <div className="p-3 border-b border-brand-ghost/30 flex items-center justify-between">
                      <span className="font-medium text-white">LinkedIn Notifications</span>
                      {linkedInWebhookEvents.length > 0 && (
                        <button
                          onClick={() => markLinkedInEventsAsRead(linkedInWebhookEvents.map(e => e.id))}
                          className="text-xs text-[#0A66C2] hover:underline"
                        >
                          Mark all read
                        </button>
                      )}
                    </div>
                    {linkedInWebhookEvents.length === 0 ? (
                      <div className="p-4 text-center text-brand-silver/70">
                        <p>No notifications yet</p>
                        <p className="text-xs mt-1">LinkedIn events will appear here</p>
                      </div>
                    ) : (
                      <div className="divide-y divide-brand-ghost/20">
                        {linkedInWebhookEvents.map(event => (
                          <div 
                            key={event.id}
                            className={`p-3 ${!event.read ? 'bg-[#0A66C2]/5' : ''} hover:bg-brand-ghost/10 cursor-pointer`}
                            onClick={() => !event.read && markLinkedInEventsAsRead([event.id])}
                          >
                            <div className="flex items-start gap-2">
                              <span className={`w-2 h-2 rounded-full mt-2 ${!event.read ? 'bg-[#0A66C2]' : 'bg-transparent'}`} />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-white">
                                  {event.event_type === 'share_reaction' && '👍 Someone reacted to your post'}
                                  {event.event_type === 'share_comment' && '💬 New comment on your post'}
                                  {event.event_type === 'mention' && '🔔 You were mentioned'}
                                  {event.event_type === 'connection_update' && '🤝 New connection update'}
                                  {event.event_type === 'share_update' && '📝 Share update'}
                                  {event.event_type === 'message' && '✉️ New message'}
                                  {event.event_type === 'organization_update' && '🏢 Organization update'}
                                </p>
                                <p className="text-xs text-brand-silver/70">
                                  {new Date(event.created_at).toLocaleString()}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
              
              <button
                onClick={() => setShowLinkedInAnalytics(!showLinkedInAnalytics)}
                className="px-3 py-1.5 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 text-brand-silver transition-colors flex items-center gap-2 text-sm"
              >
                {showLinkedInAnalytics ? 'Hide' : 'Show'}
                <svg className={`w-4 h-4 transition-transform ${showLinkedInAnalytics ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <button
                onClick={fetchLinkedInAnalytics}
                disabled={linkedInAnalyticsLoading}
                className="p-2 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 transition-colors disabled:opacity-50"
                title="Refresh analytics"
              >
                <svg className={`w-4 h-4 text-brand-silver ${linkedInAnalyticsLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          </div>

          {showLinkedInAnalytics && (
            <>
              {linkedInAnalyticsLoading && !linkedInAnalyticsData ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#0A66C2]"></div>
                </div>
              ) : linkedInAnalyticsData ? (
                <div>
                  {linkedInAnalyticsData.test_mode && (
                    <div className="mb-4 px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-400 text-sm">
                      🧪 Test Mode - Showing simulated analytics data
                    </div>
                  )}
                  
                  {/* Profile Stats */}
                  <div className="mb-4">
                    <div className="flex items-center gap-2 mb-3">
                      {linkedInAnalyticsData.profile?.picture && (
                        <img src={linkedInAnalyticsData.profile.picture} alt="" className="w-8 h-8 rounded-full" />
                      )}
                      <span className="text-sm text-white">{linkedInAnalyticsData.profile?.name || 'Your LinkedIn'}</span>
                    </div>
                    <div className="grid grid-cols-4 gap-3">
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-[#0A66C2]">{linkedInAnalyticsData.network?.connections?.toLocaleString() || 0}</div>
                        <div className="text-xs text-brand-silver/70">Connections</div>
                      </div>
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-white">{linkedInAnalyticsData.totals?.total_posts || 0}</div>
                        <div className="text-xs text-brand-silver/70">Posts</div>
                      </div>
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-white">{linkedInAnalyticsData.totals?.total_likes || 0}</div>
                        <div className="text-xs text-brand-silver/70">Likes</div>
                      </div>
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-white">{linkedInAnalyticsData.totals?.total_comments || 0}</div>
                        <div className="text-xs text-brand-silver/70">Comments</div>
                      </div>
                    </div>
                  </div>

                  {/* Engagement Summary */}
                  {linkedInAnalyticsData.totals && (
                    <div className="grid grid-cols-4 gap-2">
                      <div className="bg-gradient-to-br from-blue-500/20 to-blue-600/10 rounded-lg p-3 text-center border border-blue-500/20">
                        <div className="text-lg font-bold text-blue-400">{linkedInAnalyticsData.totals.total_likes.toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Total Likes</div>
                      </div>
                      <div className="bg-gradient-to-br from-green-500/20 to-green-600/10 rounded-lg p-3 text-center border border-green-500/20">
                        <div className="text-lg font-bold text-green-400">{linkedInAnalyticsData.totals.total_comments.toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Comments</div>
                      </div>
                      <div className="bg-gradient-to-br from-purple-500/20 to-purple-600/10 rounded-lg p-3 text-center border border-purple-500/20">
                        <div className="text-lg font-bold text-purple-400">{linkedInAnalyticsData.totals.total_posts}</div>
                        <div className="text-xs text-brand-silver/70">Posts</div>
                      </div>
                      <div className="bg-gradient-to-br from-[#0A66C2]/20 to-[#0A66C2]/10 rounded-lg p-3 text-center border border-[#0A66C2]/20">
                        <div className="text-lg font-bold text-[#0A66C2]">{linkedInAnalyticsData.totals.engagement_rate}%</div>
                        <div className="text-xs text-brand-silver/70">Engagement</div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-4 text-brand-silver/70">
                  <p>Failed to load analytics.</p>
                  <button onClick={fetchLinkedInAnalytics} className="text-[#0A66C2] hover:underline mt-1 text-sm">
                    Try again
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Facebook Analytics */}
      {profiles?.facebook?.connected && (
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-heading font-bold text-white flex items-center gap-2">
              <svg className="w-5 h-5 text-[#1877F2]" fill="currentColor" viewBox="0 0 24 24">
                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
              </svg>
              Facebook Analytics
            </h2>
            <div className="flex items-center gap-2">
              {/* Notifications Bell */}
              <div className="relative">
                <button
                  onClick={() => {
                    setShowFacebookNotifications(!showFacebookNotifications);
                    if (!showFacebookNotifications) fetchFacebookWebhookEvents();
                  }}
                  className="p-2 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 transition-colors relative"
                  title="Notifications"
                >
                  <svg className="w-5 h-5 text-brand-silver" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                  </svg>
                  {facebookUnreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                      {facebookUnreadCount > 9 ? '9+' : facebookUnreadCount}
                    </span>
                  )}
                </button>
                
                {/* Facebook Notifications Dropdown */}
                {showFacebookNotifications && (
                  <div className="absolute right-0 top-full mt-2 w-80 bg-brand-midnight border border-brand-ghost/30 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
                    <div className="p-3 border-b border-brand-ghost/20 flex items-center justify-between">
                      <span className="text-white font-medium">Facebook Notifications</span>
                      {facebookUnreadCount > 0 && (
                        <button
                          onClick={() => markFacebookEventsAsRead(facebookWebhookEvents.filter(e => !e.read).map(e => e.id))}
                          className="text-xs text-[#1877F2] hover:underline"
                        >
                          Mark all read
                        </button>
                      )}
                    </div>
                    {facebookWebhookEvents.length === 0 ? (
                      <div className="p-4 text-center text-brand-silver/70">
                        <p>No notifications yet</p>
                        <p className="text-xs mt-1">Facebook events will appear here</p>
                      </div>
                    ) : (
                      <div className="divide-y divide-brand-ghost/20">
                        {facebookWebhookEvents.map(event => (
                          <div 
                            key={event.id}
                            className={`p-3 ${!event.read ? 'bg-[#1877F2]/5' : ''} hover:bg-brand-ghost/10 cursor-pointer`}
                            onClick={() => !event.read && markFacebookEventsAsRead([event.id])}
                          >
                            <div className="flex items-start gap-2">
                              <span className={`w-2 h-2 rounded-full mt-2 ${!event.read ? 'bg-[#1877F2]' : 'bg-transparent'}`} />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-white">
                                  {event.event_type === 'feed' && '📝 New feed activity'}
                                  {event.event_type === 'reaction' && '👍 Someone reacted to your post'}
                                  {event.event_type === 'comment' && '💬 New comment on your post'}
                                  {event.event_type === 'mention' && '🔔 You were mentioned'}
                                  {event.event_type === 'message' && '✉️ New message'}
                                  {!['feed', 'reaction', 'comment', 'mention', 'message'].includes(event.event_type) && `📌 ${event.event_type}`}
                                </p>
                                <p className="text-xs text-brand-silver/70">
                                  {new Date(event.created_at).toLocaleString()}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
              
              <button
                onClick={() => setShowFacebookAnalytics(!showFacebookAnalytics)}
                className="px-3 py-1.5 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 text-brand-silver transition-colors flex items-center gap-2 text-sm"
              >
                {showFacebookAnalytics ? 'Hide' : 'Show'}
                <svg className={`w-4 h-4 transition-transform ${showFacebookAnalytics ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <button
                onClick={fetchFacebookAnalytics}
                disabled={facebookAnalyticsLoading}
                className="p-2 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 transition-colors disabled:opacity-50"
                title="Refresh analytics"
              >
                <svg className={`w-4 h-4 text-brand-silver ${facebookAnalyticsLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          </div>

          {showFacebookAnalytics && (
            <>
              {facebookAnalyticsLoading && !facebookAnalyticsData ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#1877F2]"></div>
                </div>
              ) : facebookAnalyticsData ? (
                <div>
                  {facebookAnalyticsData.test_mode && (
                    <div className="mb-4 px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-400 text-sm">
                      🧪 Test Mode - Showing simulated analytics data
                    </div>
                  )}
                  
                  {/* Page Info */}
                  <div className="mb-4">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-8 h-8 rounded-full bg-[#1877F2] flex items-center justify-center">
                        <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                        </svg>
                      </div>
                      <span className="text-sm text-white">{facebookAnalyticsData.page_name || 'Your Facebook Page'}</span>
                    </div>
                    
                    {/* Page Stats Grid */}
                    <div className="grid grid-cols-3 gap-3">
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-[#1877F2]">{(facebookAnalyticsData.insights?.page_fans || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Page Fans</div>
                      </div>
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-white">{(facebookAnalyticsData.insights?.page_fan_adds || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">New Fans</div>
                      </div>
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-white">{(facebookAnalyticsData.recent_posts?.length || 0)}</div>
                        <div className="text-xs text-brand-silver/70">Recent Posts</div>
                      </div>
                    </div>
                  </div>

                  {/* Engagement Stats */}
                  {facebookAnalyticsData.insights && (
                    <div className="grid grid-cols-4 gap-2 mb-4">
                      <div className="bg-gradient-to-br from-[#1877F2]/20 to-[#1877F2]/10 rounded-lg p-3 text-center border border-[#1877F2]/20">
                        <div className="text-lg font-bold text-[#1877F2]">{(facebookAnalyticsData.insights.page_impressions || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Impressions</div>
                      </div>
                      <div className="bg-gradient-to-br from-green-500/20 to-green-600/10 rounded-lg p-3 text-center border border-green-500/20">
                        <div className="text-lg font-bold text-green-400">{(facebookAnalyticsData.insights.page_engaged_users || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Engaged Users</div>
                      </div>
                      <div className="bg-gradient-to-br from-purple-500/20 to-purple-600/10 rounded-lg p-3 text-center border border-purple-500/20">
                        <div className="text-lg font-bold text-purple-400">{(facebookAnalyticsData.insights.page_post_engagements || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Post Engagements</div>
                      </div>
                      <div className="bg-gradient-to-br from-orange-500/20 to-orange-600/10 rounded-lg p-3 text-center border border-orange-500/20">
                        <div className="text-lg font-bold text-orange-400">{(facebookAnalyticsData.insights.page_views_total || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Page Views</div>
                      </div>
                    </div>
                  )}

                  {/* Recent Posts */}
                  {facebookAnalyticsData.recent_posts && facebookAnalyticsData.recent_posts.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-white mb-3">Recent Posts</h3>
                      <div className="space-y-3 max-h-64 overflow-y-auto">
                        {facebookAnalyticsData.recent_posts.slice(0, 5).map((post) => (
                          <div key={post.id} className="bg-brand-ghost/10 rounded-lg p-3">
                            <p className="text-sm text-white line-clamp-2 mb-2">
                              {post.message || '(No message)'}
                            </p>
                            <div className="flex items-center gap-4 text-xs text-brand-silver/70">
                              <span>👍 {post.likes}</span>
                              <span>💬 {post.comments}</span>
                              <span>🔄 {post.shares}</span>
                              <span className="ml-auto">
                                {new Date(post.created_time).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-4 text-brand-silver/70">
                  <p>Failed to load analytics.</p>
                  <button onClick={fetchFacebookAnalytics} className="text-[#1877F2] hover:underline mt-1 text-sm">
                    Try again
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Instagram Analytics */}
      {profiles?.instagram?.connected && (
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-heading font-bold text-white flex items-center gap-2">
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none">
                <defs>
                  <linearGradient id="instagramGradient" x1="0%" y1="100%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#FFDC80" />
                    <stop offset="25%" stopColor="#F77737" />
                    <stop offset="50%" stopColor="#E1306C" />
                    <stop offset="75%" stopColor="#C13584" />
                    <stop offset="100%" stopColor="#833AB4" />
                  </linearGradient>
                </defs>
                <path fill="url(#instagramGradient)" d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
              </svg>
              Instagram Analytics
            </h2>
            <div className="flex items-center gap-2">
              {/* Notifications Bell */}
              <div className="relative">
                <button
                  onClick={() => {
                    setShowInstagramNotifications(!showInstagramNotifications);
                    if (!showInstagramNotifications) fetchInstagramWebhookEvents();
                  }}
                  className="p-2 rounded-lg bg-brand-ghost/20 hover:bg-brand-ghost/30 transition-colors relative"
                  title="Notifications"
                >
                  <svg className="w-5 h-5 text-brand-silver" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                  </svg>
                  {instagramUnreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                      {instagramUnreadCount > 9 ? '9+' : instagramUnreadCount}
                    </span>
                  )}
                </button>
                
                {/* Notifications Dropdown */}
                {showInstagramNotifications && (
                  <div className="absolute right-0 top-12 w-80 bg-brand-midnight border border-brand-ghost/30 rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
                    <div className="p-3 border-b border-brand-ghost/30 flex items-center justify-between">
                      <span className="text-sm font-medium text-white">Instagram Notifications</span>
                      {instagramUnreadCount > 0 && (
                        <button
                          onClick={() => markInstagramEventsAsRead(instagramWebhookEvents.filter(e => !e.read).map(e => e.id))}
                          className="text-xs text-pink-400 hover:underline"
                        >
                          Mark all read
                        </button>
                      )}
                    </div>
                    <div className="divide-y divide-brand-ghost/20">
                      {instagramWebhookEvents.length === 0 ? (
                        <div className="p-4 text-center text-brand-silver/70 text-sm">
                          No notifications yet
                        </div>
                      ) : (
                        instagramWebhookEvents.map((event) => (
                          <div
                            key={event.id}
                            className={`p-3 ${!event.read ? 'bg-pink-500/10' : ''}`}
                            onClick={() => !event.read && markInstagramEventsAsRead([event.id])}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-white capitalize">
                                {event.event_type.replace(/_/g, ' ')}
                              </span>
                              <span className="text-xs text-brand-silver/50">
                                {new Date(event.created_at).toLocaleDateString()}
                              </span>
                            </div>
                            {!event.read && (
                              <span className="inline-block w-2 h-2 bg-pink-400 rounded-full"></span>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
              
              <button
                onClick={() => setShowInstagramAnalytics(!showInstagramAnalytics)}
                className="text-xs text-pink-400 hover:underline"
              >
                {showInstagramAnalytics ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>
          
          {showInstagramAnalytics && (
            <>
              {instagramAnalyticsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-pink-500"></div>
                </div>
              ) : instagramAnalyticsData ? (
                <div>
                  {instagramAnalyticsData.test_mode && (
                    <div className="mb-4 px-3 py-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-400 text-sm">
                      🧪 Test Mode - Showing simulated analytics data
                    </div>
                  )}
                  
                  {/* Account Info */}
                  <div className="mb-4">
                    <div className="flex items-center gap-2 mb-3">
                      {instagramAnalyticsData.profile_picture_url ? (
                        <img
                          src={instagramAnalyticsData.profile_picture_url}
                          alt={instagramAnalyticsData.username || 'Profile'}
                          className="w-8 h-8 rounded-full"
                        />
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-yellow-400 via-pink-500 to-purple-600 flex items-center justify-center">
                          <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069z"/>
                          </svg>
                        </div>
                      )}
                      <span className="text-sm text-white">@{instagramAnalyticsData.username || 'Your Instagram Account'}</span>
                    </div>
                    
                    {/* Account Stats Grid */}
                    <div className="grid grid-cols-3 gap-3">
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-pink-400">{(instagramAnalyticsData.insights?.follower_count || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Followers</div>
                      </div>
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-white">{(instagramAnalyticsData.insights?.follows_count || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Following</div>
                      </div>
                      <div className="bg-brand-ghost/10 rounded-lg p-3 text-center">
                        <div className="text-lg font-bold text-white">{(instagramAnalyticsData.insights?.media_count || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Posts</div>
                      </div>
                    </div>
                  </div>

                  {/* Engagement Stats */}
                  {instagramAnalyticsData.insights && (
                    <div className="grid grid-cols-4 gap-2 mb-4">
                      <div className="bg-gradient-to-br from-pink-500/20 to-pink-600/10 rounded-lg p-3 text-center border border-pink-500/20">
                        <div className="text-lg font-bold text-pink-400">{(instagramAnalyticsData.insights.impressions || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Impressions</div>
                      </div>
                      <div className="bg-gradient-to-br from-purple-500/20 to-purple-600/10 rounded-lg p-3 text-center border border-purple-500/20">
                        <div className="text-lg font-bold text-purple-400">{(instagramAnalyticsData.insights.reach || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Reach</div>
                      </div>
                      <div className="bg-gradient-to-br from-orange-500/20 to-orange-600/10 rounded-lg p-3 text-center border border-orange-500/20">
                        <div className="text-lg font-bold text-orange-400">{(instagramAnalyticsData.insights.profile_views || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Profile Views</div>
                      </div>
                      <div className="bg-gradient-to-br from-blue-500/20 to-blue-600/10 rounded-lg p-3 text-center border border-blue-500/20">
                        <div className="text-lg font-bold text-blue-400">{(instagramAnalyticsData.insights.website_clicks || 0).toLocaleString()}</div>
                        <div className="text-xs text-brand-silver/70">Website Clicks</div>
                      </div>
                    </div>
                  )}

                  {/* Recent Media */}
                  {instagramAnalyticsData.recent_media && instagramAnalyticsData.recent_media.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-white mb-3">Recent Posts</h3>
                      <div className="space-y-3 max-h-64 overflow-y-auto">
                        {instagramAnalyticsData.recent_media.slice(0, 5).map((media) => (
                          <div key={media.id} className="bg-brand-ghost/10 rounded-lg p-3">
                            <div className="flex items-start gap-3">
                              {media.thumbnail_url && (
                                <img
                                  src={media.thumbnail_url}
                                  alt=""
                                  className="w-12 h-12 rounded object-cover"
                                />
                              )}
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-white line-clamp-2 mb-2">
                                  {media.caption || '(No caption)'}
                                </p>
                                <div className="flex items-center gap-4 text-xs text-brand-silver/70">
                                  <span>❤️ {media.like_count}</span>
                                  <span>💬 {media.comments_count}</span>
                                  <span className="capitalize">{media.media_type.toLowerCase()}</span>
                                  <span className="ml-auto">
                                    {new Date(media.timestamp).toLocaleDateString()}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-4 text-brand-silver/70">
                  <p>Failed to load analytics.</p>
                  <button onClick={fetchInstagramAnalytics} className="text-pink-400 hover:underline mt-1 text-sm">
                    Try again
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
