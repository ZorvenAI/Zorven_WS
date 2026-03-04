'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { apiClient } from '@/lib/api';

interface PostHistory {
  id: number;
  title: string;
  content: string;
  platforms: string[];
  status: string;
  status_display: string;
  scheduled_date: string;
  published_at: string | null;
  post_results: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

type PlatformFilter = 'all' | 'linkedin' | 'twitter';
type StatusFilter = 'all' | 'published' | 'scheduled' | 'draft' | 'cancelled' | 'failed';

export default function HistoryPage() {
  useAuth();

  const [posts, setPosts] = useState<PostHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter states
  const [platformFilter, setPlatformFilter] = useState<PlatformFilter>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');

  // Pagination
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const ITEMS_PER_PAGE = 20;

  const fetchPosts = useCallback(async (resetPage = false) => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      
      if (platformFilter !== 'all') {
        params.append('platform', platformFilter);
      }
      if (statusFilter !== 'all') {
        params.append('status', statusFilter);
      }
      if (startDate) {
        params.append('start_date', startDate);
      }
      if (endDate) {
        // Add end of day to include the full day
        params.append('end_date', `${endDate}T23:59:59`);
      }

      const currentPage = resetPage ? 1 : page;
      params.append('limit', String(ITEMS_PER_PAGE * currentPage));

      const response = await apiClient.get(`/automation/content-calendar/?${params.toString()}`);
      
      if (response.ok) {
        const data = await response.json();
        const postsData = data.results || data;
        setPosts(Array.isArray(postsData) ? postsData : []);
        setHasMore(postsData.length >= ITEMS_PER_PAGE * currentPage);
        if (resetPage) {
          setPage(1);
        }
      } else {
        setError('Failed to fetch posts');
      }
    } catch (err) {
      console.error('Error fetching posts:', err);
      setError('An error occurred while fetching posts');
    } finally {
      setLoading(false);
    }
  }, [platformFilter, statusFilter, startDate, endDate, page]);

  useEffect(() => {
    fetchPosts(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platformFilter, statusFilter, startDate, endDate]);

  const loadMore = () => {
    setPage(prev => prev + 1);
  };

  useEffect(() => {
    if (page > 1) {
      fetchPosts();
    }
  }, [page, fetchPosts]);

  const clearFilters = () => {
    setPlatformFilter('all');
    setStatusFilter('all');
    setStartDate('');
    setEndDate('');
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'published':
        return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'scheduled':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      case 'draft':
        return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
      case 'cancelled':
        return 'bg-red-500/20 text-red-400 border-red-500/30';
      case 'failed':
        return 'bg-red-500/20 text-red-400 border-red-500/30';
      default:
        return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
    }
  };

  const getPlatformIcon = (platform: string) => {
    if (platform === 'linkedin') {
      return (
        <div className="p-1.5 rounded bg-[#0A66C2]" title="LinkedIn">
          <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
            <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
          </svg>
        </div>
      );
    }
    if (platform === 'twitter') {
      return (
        <div className="p-1.5 rounded bg-black" title="Twitter/X">
          <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
            <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
          </svg>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="min-h-screen bg-brand-midnight">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <Link 
            href="/automation" 
            className="text-brand-electric hover:text-brand-electric/80 flex items-center gap-2 mb-4"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Automation
          </Link>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-heading font-bold text-white">Post History</h1>
              <p className="text-brand-silver/70 mt-2">
                View and filter all your social media posts
              </p>
            </div>
            <div className="text-sm text-brand-silver">
              {posts.length} post{posts.length !== 1 ? 's' : ''} found
            </div>
          </div>
        </div>

        {/* Filters Section */}
        <div className="glass-card p-6 mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading text-lg font-medium text-white flex items-center gap-2">
              <svg className="w-5 h-5 text-brand-electric" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
              </svg>
              Filters
            </h2>
            <button
              onClick={clearFilters}
              className="text-sm text-brand-silver hover:text-white transition-colors"
            >
              Clear all
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Platform Filter */}
            <div>
              <label className="block text-sm font-medium text-brand-silver mb-2">Platform</label>
              <select
                value={platformFilter}
                onChange={(e) => setPlatformFilter(e.target.value as PlatformFilter)}
                className="w-full bg-brand-midnight border border-brand-ghost/30 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-brand-electric/50"
              >
                <option value="all">All Platforms</option>
                <option value="linkedin">LinkedIn</option>
                <option value="twitter">Twitter/X</option>
              </select>
            </div>

            {/* Status Filter */}
            <div>
              <label className="block text-sm font-medium text-brand-silver mb-2">Status</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                className="w-full bg-brand-midnight border border-brand-ghost/30 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-brand-electric/50"
              >
                <option value="all">All Statuses</option>
                <option value="published">Published</option>
                <option value="scheduled">Scheduled</option>
                <option value="draft">Draft</option>
                <option value="cancelled">Cancelled</option>
                <option value="failed">Failed</option>
              </select>
            </div>

            {/* Start Date */}
            <div>
              <label className="block text-sm font-medium text-brand-silver mb-2">From Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full bg-brand-midnight border border-brand-ghost/30 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-brand-electric/50"
              />
            </div>

            {/* End Date */}
            <div>
              <label className="block text-sm font-medium text-brand-silver mb-2">To Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                min={startDate || undefined}
                className="w-full bg-brand-midnight border border-brand-ghost/30 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-brand-electric/50"
              />
            </div>
          </div>
        </div>

        {/* Posts List */}
        {loading && posts.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin w-8 h-8 border-2 border-brand-electric border-t-transparent rounded-full"></div>
          </div>
        ) : error ? (
          <div className="glass-card p-8 text-center">
            <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="font-heading text-lg font-medium text-white mb-2">Error Loading Posts</h3>
            <p className="text-brand-silver/70">{error}</p>
            <button
              onClick={() => fetchPosts(true)}
              className="mt-4 btn-primary"
            >
              Try Again
            </button>
          </div>
        ) : posts.length === 0 ? (
          <div className="glass-card p-8 text-center">
            <div className="w-16 h-16 bg-brand-ghost/20 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-brand-silver" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="font-heading text-lg font-medium text-white mb-2">No Posts Found</h3>
            <p className="text-brand-silver/70">
              {platformFilter !== 'all' || statusFilter !== 'all' || startDate || endDate
                ? 'Try adjusting your filters to see more results.'
                : 'Start creating posts to see them appear here.'}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {posts.map((post) => (
              <div 
                key={post.id} 
                className={`glass-card p-5 border ${
                  post.status === 'published' 
                    ? 'border-green-500/20' 
                    : post.status === 'failed' || post.status === 'cancelled'
                    ? 'border-red-500/20'
                    : 'border-brand-ghost/20'
                }`}
              >
                <div className="flex items-start gap-4">
                  {/* Platform Icons */}
                  <div className="flex flex-col gap-2 flex-shrink-0">
                    {post.platforms.map((platform) => (
                      <div key={platform}>
                        {getPlatformIcon(platform)}
                      </div>
                    ))}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-heading text-white font-medium">{post.title}</h3>
                          <span className={`text-xs px-2 py-0.5 rounded-full border ${getStatusColor(post.status)}`}>
                            {post.status_display || post.status}
                          </span>
                        </div>
                        <p className="text-brand-silver/70 text-sm mt-2 line-clamp-3">
                          {post.content}
                        </p>
                      </div>
                    </div>

                    {/* Metadata */}
                    <div className="flex items-center gap-4 mt-4 text-xs text-brand-silver/50">
                      <span className="flex items-center gap-1">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        {post.status === 'published' && post.published_at 
                          ? `Published: ${new Date(post.published_at).toLocaleString()}`
                          : `Scheduled: ${new Date(post.scheduled_date).toLocaleString()}`
                        }
                      </span>
                      <span className="flex items-center gap-1">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Created: {new Date(post.created_at).toLocaleDateString()}
                      </span>
                      {post.post_results && Object.keys(post.post_results).length > 0 && (
                        <span className="flex items-center gap-1 text-green-400">
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          Has results
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {/* Load More Button */}
            {hasMore && (
              <div className="text-center pt-4">
                <button
                  onClick={loadMore}
                  disabled={loading}
                  className="btn-secondary"
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Loading...
                    </span>
                  ) : (
                    'Load More'
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
