'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

interface FileFiltersBarProps {
  onSearchChange: (search: string) => void;
  onFileTypeChange: (type: string) => void;
  onStatusChange: (status: string) => void;
  onSortChange: (sortBy: string, sortOrder: 'asc' | 'desc') => void;
  initialSearch?: string;
  initialFileType?: string;
  initialStatus?: string;
  initialSortBy?: string;
  initialSortOrder?: 'asc' | 'desc';
  showFilters?: boolean;
}

export function FileFiltersBar({
  onSearchChange,
  onFileTypeChange,
  onStatusChange,
  onSortChange,
  initialSearch = '',
  initialFileType = '',
  initialStatus = '',
  initialSortBy = 'uploaded_at',
  initialSortOrder = 'desc',
  showFilters = true,
}: FileFiltersBarProps) {
  const [search, setSearch] = useState(initialSearch);
  const [fileType, setFileType] = useState(initialFileType);
  const [status, setStatus] = useState(initialStatus);
  const [sortBy, setSortBy] = useState(initialSortBy);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(initialSortOrder);
  const [showAdvanced, setShowAdvanced] = useState(false);
  
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Debounced search
  const debouncedSearch = useCallback(
    (value: string) => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
      searchTimeoutRef.current = setTimeout(() => {
        onSearchChange(value);
      }, 300);
    },
    [onSearchChange]
  );

  useEffect(() => {
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, []);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearch(value);
    debouncedSearch(value);
  };

  const handleFileTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    setFileType(value);
    onFileTypeChange(value);
  };

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    setStatus(value);
    onStatusChange(value);
  };

  const handleSortByChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    setSortBy(value);
    onSortChange(value, sortOrder);
  };

  const handleSortOrderToggle = () => {
    const newOrder = sortOrder === 'desc' ? 'asc' : 'desc';
    setSortOrder(newOrder);
    onSortChange(sortBy, newOrder);
  };

  const clearFilters = () => {
    setSearch('');
    setFileType('');
    setStatus('');
    setSortBy('uploaded_at');
    setSortOrder('desc');
    onSearchChange('');
    onFileTypeChange('');
    onStatusChange('');
    onSortChange('uploaded_at', 'desc');
  };

  const hasActiveFilters = search || fileType || status || sortBy !== 'uploaded_at' || sortOrder !== 'desc';

  return (
    <div className="space-y-3">
      {/* Search bar */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={search}
            onChange={handleSearchChange}
            placeholder="Search files..."
            className="w-full px-4 py-2 pl-10 text-sm rounded-lg border border-white/20 bg-brand-dark text-white placeholder:text-brand-silver/50 focus:outline-none focus:border-brand-electric"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-silver/50">
            🔍
          </span>
          {search && (
            <button
              onClick={() => {
                setSearch('');
                onSearchChange('');
              }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-brand-silver/50 hover:text-white"
            >
              ✕
            </button>
          )}
        </div>

        {showFilters && (
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className={`px-3 py-2 text-sm rounded-lg border transition-colors ${
              showAdvanced || hasActiveFilters
                ? 'border-brand-electric bg-brand-electric/20 text-brand-electric'
                : 'border-white/20 bg-white/5 text-white hover:bg-white/10'
            }`}
          >
            ⚙️ Filters {hasActiveFilters && '•'}
          </button>
        )}
      </div>

      {/* Advanced filters */}
      {showFilters && showAdvanced && (
        <div className="flex flex-wrap gap-3 p-3 rounded-lg bg-white/5 border border-white/10">
          {/* File Type filter */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-brand-silver/70">Type:</label>
            <select
              value={fileType}
              onChange={handleFileTypeChange}
              className="px-2 py-1 text-sm rounded border border-white/20 bg-brand-dark text-white focus:outline-none focus:border-brand-electric"
            >
              <option value="">All</option>
              <option value="image">Image</option>
              <option value="video">Video</option>
              <option value="document">Document</option>
              <option value="other">Other</option>
            </select>
          </div>

          {/* Status filter */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-brand-silver/70">Status:</label>
            <select
              value={status}
              onChange={handleStatusChange}
              className="px-2 py-1 text-sm rounded border border-white/20 bg-brand-dark text-white focus:outline-none focus:border-brand-electric"
            >
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="ingested">Ingested</option>
              <option value="curated">Curated</option>
              <option value="indexed">Indexed</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          {/* Sort by */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-brand-silver/70">Sort:</label>
            <select
              value={sortBy}
              onChange={handleSortByChange}
              className="px-2 py-1 text-sm rounded border border-white/20 bg-brand-dark text-white focus:outline-none focus:border-brand-electric"
            >
              <option value="uploaded_at">Upload Date</option>
              <option value="file_name">File Name</option>
              <option value="file_size">File Size</option>
            </select>
            <button
              onClick={handleSortOrderToggle}
              className="px-2 py-1 text-sm rounded border border-white/20 bg-white/5 text-white hover:bg-white/10 transition-colors"
              title={sortOrder === 'desc' ? 'Descending' : 'Ascending'}
            >
              {sortOrder === 'desc' ? '↓' : '↑'}
            </button>
          </div>

          {/* Clear filters */}
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="px-3 py-1 text-sm rounded border border-red-500/50 bg-red-500/20 text-red-300 hover:bg-red-500/30 transition-colors"
            >
              Clear All
            </button>
          )}
        </div>
      )}
    </div>
  );
}
