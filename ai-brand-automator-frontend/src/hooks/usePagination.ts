'use client';

import { useState, useCallback, useMemo } from 'react';

interface UsePaginationOptions {
  defaultPage?: number;
  defaultPageSize?: number;
  maxPageSize?: number;
}

interface UsePaginationReturn {
  // Pagination state
  currentPage: number;
  pageSize: number;
  totalCount: number;
  totalPages: number;
  hasNext: boolean;
  hasPrevious: boolean;

  // Setters
  setCurrentPage: (page: number) => void;
  setPageSize: (size: number) => void;

  // Update from API response
  updateFromResponse: (response: {
    count: number;
    total_pages: number;
    current_page: number;
    page_size: number;
    has_next: boolean;
    has_previous: boolean;
  }) => void;

  // Navigation helpers
  goToFirstPage: () => void;
  goToLastPage: () => void;
  goToNextPage: () => void;
  goToPreviousPage: () => void;
  goToPage: (page: number) => void;

  // Reset
  reset: () => void;

  // Computed values
  startItem: number;
  endItem: number;
  pageRange: number[];
}

/**
 * Hook for managing pagination state
 * Used by file browser and other paginated components
 */
export function usePagination(options: UsePaginationOptions = {}): UsePaginationReturn {
  const {
    defaultPage = 1,
    defaultPageSize = 10,
    maxPageSize = 50,
  } = options;

  const [currentPage, setCurrentPage] = useState(defaultPage);
  const [pageSize, setPageSizeInternal] = useState(defaultPageSize);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrevious, setHasPrevious] = useState(false);

  const setPageSize = useCallback(
    (size: number) => {
      const clampedSize = Math.min(Math.max(1, size), maxPageSize);
      setPageSizeInternal(clampedSize);
      // Reset to first page when page size changes
      setCurrentPage(1);
    },
    [maxPageSize]
  );

  const updateFromResponse = useCallback(
    (response: {
      count: number;
      total_pages: number;
      current_page: number;
      page_size: number;
      has_next: boolean;
      has_previous: boolean;
    }) => {
      setTotalCount(response.count);
      setTotalPages(response.total_pages);
      setCurrentPage(response.current_page);
      setPageSizeInternal(response.page_size);
      setHasNext(response.has_next);
      setHasPrevious(response.has_previous);
    },
    []
  );

  const goToFirstPage = useCallback(() => {
    setCurrentPage(1);
  }, []);

  const goToLastPage = useCallback(() => {
    setCurrentPage(totalPages);
  }, [totalPages]);

  const goToNextPage = useCallback(() => {
    if (hasNext) {
      setCurrentPage((prev) => Math.min(prev + 1, totalPages));
    }
  }, [hasNext, totalPages]);

  const goToPreviousPage = useCallback(() => {
    if (hasPrevious) {
      setCurrentPage((prev) => Math.max(prev - 1, 1));
    }
  }, [hasPrevious]);

  const goToPage = useCallback(
    (page: number) => {
      const clampedPage = Math.min(Math.max(1, page), totalPages);
      setCurrentPage(clampedPage);
    },
    [totalPages]
  );

  const reset = useCallback(() => {
    setCurrentPage(defaultPage);
    setPageSizeInternal(defaultPageSize);
    setTotalCount(0);
    setTotalPages(1);
    setHasNext(false);
    setHasPrevious(false);
  }, [defaultPage, defaultPageSize]);

  // Calculate start/end item numbers for display
  const startItem = useMemo(() => {
    if (totalCount === 0) return 0;
    return (currentPage - 1) * pageSize + 1;
  }, [currentPage, pageSize, totalCount]);

  const endItem = useMemo(() => {
    return Math.min(currentPage * pageSize, totalCount);
  }, [currentPage, pageSize, totalCount]);

  // Calculate page range for pagination buttons (show max 5 pages)
  const pageRange = useMemo(() => {
    const range: number[] = [];
    let start = Math.max(1, currentPage - 2);
    let end = Math.min(totalPages, currentPage + 2);

    // Adjust if we're near the start or end
    if (currentPage <= 3) {
      end = Math.min(5, totalPages);
    }
    if (currentPage >= totalPages - 2) {
      start = Math.max(1, totalPages - 4);
    }

    for (let i = start; i <= end; i++) {
      range.push(i);
    }
    return range;
  }, [currentPage, totalPages]);

  return {
    currentPage,
    pageSize,
    totalCount,
    totalPages,
    hasNext,
    hasPrevious,
    setCurrentPage,
    setPageSize,
    updateFromResponse,
    goToFirstPage,
    goToLastPage,
    goToNextPage,
    goToPreviousPage,
    goToPage,
    reset,
    startItem,
    endItem,
    pageRange,
  };
}
