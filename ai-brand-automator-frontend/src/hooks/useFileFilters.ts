'use client';

import { useState, useCallback, useMemo } from 'react';
import { AssetsListParams } from '@/lib/api';

interface UseFileFiltersOptions {
  defaultSortBy?: 'uploaded_at' | 'file_name' | 'file_size';
  defaultSortOrder?: 'asc' | 'desc';
  defaultFileType?: string;
  defaultStatus?: string;
}

interface UseFileFiltersReturn {
  // Filter values
  search: string;
  fileType: string;
  status: string;
  sortBy: 'uploaded_at' | 'file_name' | 'file_size';
  sortOrder: 'asc' | 'desc';

  // Setters
  setSearch: (value: string) => void;
  setFileType: (value: string) => void;
  setStatus: (value: string) => void;
  setSortBy: (value: 'uploaded_at' | 'file_name' | 'file_size') => void;
  setSortOrder: (value: 'asc' | 'desc') => void;
  setSort: (sortBy: string, sortOrder: 'asc' | 'desc') => void;

  // Actions
  clearFilters: () => void;
  hasActiveFilters: boolean;

  // Get params for API call
  getApiParams: (additionalParams?: Partial<AssetsListParams>) => AssetsListParams;
}

/**
 * Hook for managing file filter state
 * Used by file browser components
 */
export function useFileFilters(options: UseFileFiltersOptions = {}): UseFileFiltersReturn {
  const {
    defaultSortBy = 'uploaded_at',
    defaultSortOrder = 'desc',
    defaultFileType = '',
    defaultStatus = '',
  } = options;

  const [search, setSearch] = useState('');
  const [fileType, setFileType] = useState(defaultFileType);
  const [status, setStatus] = useState(defaultStatus);
  const [sortBy, setSortBy] = useState<'uploaded_at' | 'file_name' | 'file_size'>(defaultSortBy);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(defaultSortOrder);

  const setSort = useCallback((newSortBy: string, newSortOrder: 'asc' | 'desc') => {
    if (newSortBy === 'uploaded_at' || newSortBy === 'file_name' || newSortBy === 'file_size') {
      setSortBy(newSortBy);
    }
    setSortOrder(newSortOrder);
  }, []);

  const clearFilters = useCallback(() => {
    setSearch('');
    setFileType(defaultFileType);
    setStatus(defaultStatus);
    setSortBy(defaultSortBy);
    setSortOrder(defaultSortOrder);
  }, [defaultFileType, defaultStatus, defaultSortBy, defaultSortOrder]);

  const hasActiveFilters = useMemo(() => {
    return (
      search !== '' ||
      fileType !== defaultFileType ||
      status !== defaultStatus ||
      sortBy !== defaultSortBy ||
      sortOrder !== defaultSortOrder
    );
  }, [search, fileType, status, sortBy, sortOrder, defaultFileType, defaultStatus, defaultSortBy, defaultSortOrder]);

  const getApiParams = useCallback(
    (additionalParams: Partial<AssetsListParams> = {}): AssetsListParams => {
      const params: AssetsListParams = {
        sort_by: sortBy,
        sort_order: sortOrder,
        ...additionalParams,
      };

      if (search) params.search = search;
      if (fileType) params.file_type = fileType;
      if (status) params.status = status;

      return params;
    },
    [search, fileType, status, sortBy, sortOrder]
  );

  return {
    search,
    fileType,
    status,
    sortBy,
    sortOrder,
    setSearch,
    setFileType,
    setStatus,
    setSortBy,
    setSortOrder,
    setSort,
    clearFilters,
    hasActiveFilters,
    getApiParams,
  };
}
