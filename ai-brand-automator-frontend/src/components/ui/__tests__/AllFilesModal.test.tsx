/**
 * Phase 7.3: Frontend Unit Tests - AllFilesModal Component
 *
 * Tests for src/components/ui/AllFilesModal.tsx
 *
 * The component uses apiClient.get/delete directly (not assetsApi),
 * renders an inline modal (no role="dialog"), uses native confirm()
 * for deletion, and delegates filtering to FileFiltersBar.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { AllFilesModal } from '../AllFilesModal';

// Mock apiClient — the component imports it directly, not assetsApi
jest.mock('@/lib/api', () => ({
  apiClient: {
    get: jest.fn(),
    delete: jest.fn(),
  },
}));

// Mock the Pagination component to simplify tests
jest.mock('@/components/ui/Pagination', () => ({
  Pagination: ({ currentPage, totalPages, hasNext, hasPrevious, onPageChange, totalCount }: {
    currentPage: number;
    totalPages: number;
    hasNext: boolean;
    hasPrevious: boolean;
    onPageChange: (page: number) => void;
    totalCount?: number;
  }) => (
    <div data-testid="pagination">
      <span>Showing page {currentPage} of {totalPages} ({totalCount} total)</span>
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={!hasPrevious}
      >
        Prev
      </button>
      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={!hasNext}
      >
        Next
      </button>
    </div>
  ),
}));

import { apiClient } from '@/lib/api';

const mockFiles = [
  {
    id: '1',
    file_name: 'logo.png',
    file_type: 'image',
    file_size: 102400,
    pipeline_status: 'indexed',
    uploaded_at: '2025-01-20T10:00:00Z',
    gcs_path: 'gs://bucket/logo.png',
  },
  {
    id: '2',
    file_name: 'video.mp4',
    file_type: 'video',
    file_size: 5242880,
    pipeline_status: 'pending',
    uploaded_at: '2025-01-19T15:00:00Z',
    gcs_path: 'gs://bucket/video.mp4',
  },
  {
    id: '3',
    file_name: 'document.pdf',
    file_type: 'document',
    file_size: 256000,
    pipeline_status: 'indexed',
    uploaded_at: '2025-01-18T09:00:00Z',
    gcs_path: 'gs://bucket/document.pdf',
  },
];

/** Build a Response-like object for apiClient mock */
function mockResponse(data: unknown, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(data),
  };
}

const filesResponse = {
  count: 3,
  total_pages: 1,
  current_page: 1,
  page_size: 10,
  has_next: false,
  has_previous: false,
  results: mockFiles,
  filters_applied: {
    search: null,
    file_type: null,
    status: null,
    sort_by: 'uploaded_at',
    sort_order: 'desc',
  },
};

describe('AllFilesModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.restoreAllMocks();
    (apiClient.get as jest.Mock).mockResolvedValue(mockResponse(filesResponse));
    (apiClient.delete as jest.Mock).mockResolvedValue(mockResponse({}, true));
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Modal Display', () => {
    it('renders modal when open', async () => {
      render(<AllFilesModal {...defaultProps} />);

      expect(screen.getByText('All Files')).toBeInTheDocument();
      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalled();
      });
    });

    it('does not render when closed', () => {
      render(<AllFilesModal {...defaultProps} isOpen={false} />);

      expect(screen.queryByText('All Files')).not.toBeInTheDocument();
    });

    it('displays modal title', async () => {
      render(<AllFilesModal {...defaultProps} />);

      expect(screen.getByText('All Files')).toBeInTheDocument();
      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalled();
      });
    });

    it('has close button', async () => {
      render(<AllFilesModal {...defaultProps} />);

      // The close button renders a "X" character
      const buttons = screen.getAllByRole('button');
      const closeButton = buttons.find(b => b.textContent?.trim() === '✕');
      expect(closeButton).toBeTruthy();

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalled();
      });
    });

    it('calls onClose when close button clicked', async () => {
      const onClose = jest.fn();
      render(<AllFilesModal {...defaultProps} onClose={onClose} />);

      const buttons = screen.getAllByRole('button');
      const closeButton = buttons.find(b => b.textContent?.trim() === '✕');
      fireEvent.click(closeButton!);

      expect(onClose).toHaveBeenCalled();

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalled();
      });
    });
  });

  describe('Data Loading', () => {
    it('shows loading state initially', async () => {
      (apiClient.get as jest.Mock).mockImplementation(
        () => new Promise(resolve => setTimeout(() => resolve(mockResponse(filesResponse)), 200))
      );

      render(<AllFilesModal {...defaultProps} />);

      // Loading state shows a spinner (no text), verify spinner container exists
      const spinnerDiv = document.querySelector('.animate-spin');
      expect(spinnerDiv).toBeTruthy();

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalled();
      });
    });

    it('loads files on mount', async () => {
      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          expect.stringContaining('/assets/')
        );
      });
    });

    it('displays files after loading', async () => {
      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
        expect(screen.getByText('video.mp4')).toBeInTheDocument();
        expect(screen.getByText('document.pdf')).toBeInTheDocument();
      });
    });

    it('shows total file count via pagination', async () => {
      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        // Pagination component shows total count
        expect(screen.getByText(/3 total/)).toBeInTheDocument();
      });
    });

    it('shows empty state when no files', async () => {
      (apiClient.get as jest.Mock).mockResolvedValue(mockResponse({
        ...filesResponse,
        count: 0,
        results: [],
      }));

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText(/no files/i)).toBeInTheDocument();
      });
    });

    it('shows error state on load failure', async () => {
      (apiClient.get as jest.Mock).mockRejectedValue(new Error('API Error'));

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText(/error|failed/i)).toBeInTheDocument();
      });
    });

    it('shows error when response is not ok', async () => {
      (apiClient.get as jest.Mock).mockResolvedValue(mockResponse({}, false));

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText(/failed to load files/i)).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    it('renders search input', async () => {
      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
      });
    });

    it('re-fetches files when search changes', async () => {
      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search/i);
      fireEvent.change(searchInput, { target: { value: 'logo' } });

      // Component debounces search, then sets the search state which triggers fetchFiles
      await waitFor(() => {
        // At least 2 calls: initial load + filter change
        expect((apiClient.get as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(2);
      });
    });

    it('renders filter controls', async () => {
      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      // FileFiltersBar should show the Filters toggle button
      expect(screen.getByText(/filters/i)).toBeInTheDocument();
    });
  });

  describe('Pagination', () => {
    it('renders pagination when there are files', async () => {
      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByTestId('pagination')).toBeInTheDocument();
      });
    });

    it('navigates to next page', async () => {
      (apiClient.get as jest.Mock).mockResolvedValue(mockResponse({
        ...filesResponse,
        count: 25,
        total_pages: 3,
        has_next: true,
      }));

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /next/i }));

      await waitFor(() => {
        // Should have been called again with page=2
        const calls = (apiClient.get as jest.Mock).mock.calls;
        const lastCall = calls[calls.length - 1][0] as string;
        expect(lastCall).toContain('page=2');
      });
    });

    it('shows current page info', async () => {
      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText(/page 1/i)).toBeInTheDocument();
      });
    });
  });

  describe('File Actions', () => {
    it('can view file', async () => {
      (apiClient.get as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('signed-url')) {
          return Promise.resolve(mockResponse({
            view_url: 'https://storage.googleapis.com/view-url',
            download_url: 'https://storage.googleapis.com/download-url',
            expires_at: '2025-01-20T10:45:00Z',
          }));
        }
        return Promise.resolve(mockResponse(filesResponse));
      });

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      // View buttons have title="View file"
      const viewButtons = screen.getAllByTitle('View file');
      fireEvent.click(viewButtons[0]);

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          expect.stringContaining('signed-url')
        );
      });
    });

    it('can delete file with confirmation', async () => {
      jest.spyOn(window, 'confirm').mockReturnValue(true);

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      // Delete buttons have title="Delete file"
      const deleteButtons = screen.getAllByTitle('Delete file');
      fireEvent.click(deleteButtons[0]);

      await waitFor(() => {
        expect(window.confirm).toHaveBeenCalled();
        expect(apiClient.delete).toHaveBeenCalledWith('/assets/1/');
      });
    });

    it('does not delete when user cancels', async () => {
      jest.spyOn(window, 'confirm').mockReturnValue(false);

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      const deleteButtons = screen.getAllByTitle('Delete file');
      fireEvent.click(deleteButtons[0]);

      expect(window.confirm).toHaveBeenCalled();
      expect(apiClient.delete).not.toHaveBeenCalled();
    });

    it('refreshes list after delete', async () => {
      jest.spyOn(window, 'confirm').mockReturnValue(true);

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      const initialCallCount = (apiClient.get as jest.Mock).mock.calls.length;

      const deleteButtons = screen.getAllByTitle('Delete file');
      fireEvent.click(deleteButtons[0]);

      await waitFor(() => {
        // Should have fetched files again after delete
        expect((apiClient.get as jest.Mock).mock.calls.length).toBeGreaterThan(initialCallCount);
      });
    });

    it('uses onDelete prop when provided', async () => {
      jest.spyOn(window, 'confirm').mockReturnValue(true);
      const onDelete = jest.fn().mockResolvedValue(undefined);

      render(<AllFilesModal {...defaultProps} onDelete={onDelete} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      const deleteButtons = screen.getAllByTitle('Delete file');
      fireEvent.click(deleteButtons[0]);

      await waitFor(() => {
        // onDelete receives (fileId, fileName)
        expect(onDelete).toHaveBeenCalledWith('1', 'logo.png');
      });
    });
  });

  describe('File Preview', () => {
    it('opens preview modal on view click', async () => {
      (apiClient.get as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('signed-url')) {
          return Promise.resolve(mockResponse({
            view_url: 'https://storage.googleapis.com/view-url',
            download_url: 'https://storage.googleapis.com/download-url',
            expires_at: '2025-01-20T10:45:00Z',
          }));
        }
        return Promise.resolve(mockResponse(filesResponse));
      });

      render(<AllFilesModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      const viewButtons = screen.getAllByTitle('View file');
      fireEvent.click(viewButtons[0]);

      await waitFor(() => {
        // Preview modal shows download link
        expect(screen.getByText('Download')).toBeInTheDocument();
        expect(screen.getByText('Open in New Tab')).toBeInTheDocument();
      });
    });
  });
});
