'use client';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  hasNext: boolean;
  hasPrevious: boolean;
  onPageChange: (page: number) => void;
  pageSize?: number;
  onPageSizeChange?: (size: number) => void;
  totalCount?: number;
  showPageSize?: boolean;
}

export function Pagination({
  currentPage,
  totalPages,
  hasNext,
  hasPrevious,
  onPageChange,
  pageSize = 10,
  onPageSizeChange,
  totalCount,
  showPageSize = true,
}: PaginationProps) {
  const pageSizeOptions = [10, 25, 50];

  // Calculate page range to display (show max 5 pages)
  const getPageRange = () => {
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
  };

  const pageRange = getPageRange();

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-3">
      {/* Results summary */}
      {totalCount !== undefined && (
        <div className="text-sm text-brand-silver/70">
          Showing page {currentPage} of {totalPages} ({totalCount} total)
        </div>
      )}

      {/* Pagination controls */}
      <div className="flex items-center gap-2">
        {/* First page */}
        <button
          onClick={() => onPageChange(1)}
          disabled={!hasPrevious}
          className="px-2 py-1 text-sm rounded border border-white/20 bg-white/5 text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/10 transition-colors"
          title="First page"
        >
          ⏮
        </button>

        {/* Previous page */}
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!hasPrevious}
          className="px-3 py-1 text-sm rounded border border-white/20 bg-white/5 text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/10 transition-colors"
        >
          ← Prev
        </button>

        {/* Page numbers */}
        <div className="hidden sm:flex items-center gap-1">
          {pageRange[0] > 1 && (
            <>
              <button
                onClick={() => onPageChange(1)}
                className="px-3 py-1 text-sm rounded border border-white/20 bg-white/5 text-white hover:bg-white/10 transition-colors"
              >
                1
              </button>
              {pageRange[0] > 2 && (
                <span className="px-2 text-brand-silver/50">...</span>
              )}
            </>
          )}

          {pageRange.map((page) => (
            <button
              key={page}
              onClick={() => onPageChange(page)}
              className={`px-3 py-1 text-sm rounded border transition-colors ${
                page === currentPage
                  ? 'border-brand-electric bg-brand-electric text-white'
                  : 'border-white/20 bg-white/5 text-white hover:bg-white/10'
              }`}
            >
              {page}
            </button>
          ))}

          {pageRange[pageRange.length - 1] < totalPages && (
            <>
              {pageRange[pageRange.length - 1] < totalPages - 1 && (
                <span className="px-2 text-brand-silver/50">...</span>
              )}
              <button
                onClick={() => onPageChange(totalPages)}
                className="px-3 py-1 text-sm rounded border border-white/20 bg-white/5 text-white hover:bg-white/10 transition-colors"
              >
                {totalPages}
              </button>
            </>
          )}
        </div>

        {/* Mobile page indicator */}
        <span className="sm:hidden text-sm text-brand-silver/70">
          {currentPage} / {totalPages}
        </span>

        {/* Next page */}
        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!hasNext}
          className="px-3 py-1 text-sm rounded border border-white/20 bg-white/5 text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/10 transition-colors"
        >
          Next →
        </button>

        {/* Last page */}
        <button
          onClick={() => onPageChange(totalPages)}
          disabled={!hasNext}
          className="px-2 py-1 text-sm rounded border border-white/20 bg-white/5 text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/10 transition-colors"
          title="Last page"
        >
          ⏭
        </button>
      </div>

      {/* Page size selector */}
      {showPageSize && onPageSizeChange && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-brand-silver/70">Per page:</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="px-2 py-1 text-sm rounded border border-white/20 bg-brand-dark text-white focus:outline-none focus:border-brand-electric"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
