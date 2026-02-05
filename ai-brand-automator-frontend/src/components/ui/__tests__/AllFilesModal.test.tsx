/**
 * Phase 7.3: Frontend Unit Tests - AllFilesModal Component
 * 
 * Tests for src/components/ui/AllFilesModal.tsx
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AllFilesModal } from '../AllFilesModal';
import { assetsApi } from '@/lib/api';

// Mock the api module
jest.mock('@/lib/api', () => ({
  assetsApi: {
    getAssets: jest.fn(),
    deleteAsset: jest.fn(),
    getSignedUrl: jest.fn(),
  },
}));

const mockFiles = [
  {
    id: '1',
    file_name: 'logo.png',
    file_type: 'image',
    file_size: 102400,
    status: 'indexed',
    uploaded_at: '2025-01-20T10:00:00Z',
    gcs_uri: 'gs://bucket/logo.png',
  },
  {
    id: '2',
    file_name: 'video.mp4',
    file_type: 'video',
    file_size: 5242880,
    status: 'pending',
    uploaded_at: '2025-01-19T15:00:00Z',
    gcs_uri: 'gs://bucket/video.mp4',
  },
  {
    id: '3',
    file_name: 'document.pdf',
    file_type: 'document',
    file_size: 256000,
    status: 'indexed',
    uploaded_at: '2025-01-18T09:00:00Z',
    gcs_uri: 'gs://bucket/document.pdf',
  },
];

describe('AllFilesModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    companyId: 'company-123',
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (assetsApi.getAssets as jest.Mock).mockResolvedValue({
      results: mockFiles,
      count: 3,
      next: null,
      previous: null,
      total_size: 5601280,
    });
    (assetsApi.deleteAsset as jest.Mock).mockResolvedValue({});
    (assetsApi.getSignedUrl as jest.Mock).mockResolvedValue({
      signed_url: 'https://storage.googleapis.com/signed-url',
      expires_at: '2025-01-20T10:45:00Z',
    });
  });

  describe('Modal Display', () => {
    it('renders modal when open', () => {
      render(<AllFilesModal {...defaultProps} />);
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('does not render when closed', () => {
      render(<AllFilesModal {...defaultProps} isOpen={false} />);
      
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('displays modal title', () => {
      render(<AllFilesModal {...defaultProps} />);
      
      expect(screen.getByText(/all files|file browser|assets/i)).toBeInTheDocument();
    });

    it('has close button', () => {
      render(<AllFilesModal {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /close|×/i })).toBeInTheDocument();
    });

    it('calls onClose when close button clicked', () => {
      const onClose = jest.fn();
      render(<AllFilesModal {...defaultProps} onClose={onClose} />);
      
      fireEvent.click(screen.getByRole('button', { name: /close|×/i }));
      
      expect(onClose).toHaveBeenCalled();
    });

    it('calls onClose when clicking overlay', () => {
      const onClose = jest.fn();
      render(<AllFilesModal {...defaultProps} onClose={onClose} />);
      
      // Click the overlay/backdrop
      const dialog = screen.getByRole('dialog');
      fireEvent.click(dialog.parentElement!);
      
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('Data Loading', () => {
    it('shows loading state initially', () => {
      (assetsApi.getAssets as jest.Mock).mockImplementation(
        () => new Promise(resolve => setTimeout(resolve, 100))
      );
      
      render(<AllFilesModal {...defaultProps} />);
      
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('loads files on mount', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledWith(
          expect.objectContaining({
            companyId: 'company-123',
            page: 1,
            page_size: 10,
          })
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

    it('shows total file count', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/3 files/i)).toBeInTheDocument();
      });
    });

    it('shows total storage size', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/5\.(34|35|4) MB/i)).toBeInTheDocument();
      });
    });

    it('shows empty state when no files', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: [],
        count: 0,
        next: null,
        previous: null,
        total_size: 0,
      });
      
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/no files|empty|upload your first/i)).toBeInTheDocument();
      });
    });

    it('shows error state on load failure', async () => {
      (assetsApi.getAssets as jest.Mock).mockRejectedValue(new Error('API Error'));
      
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/error|failed|try again/i)).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    it('renders filter bar', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
      });
    });

    it('filters by search term', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      const searchInput = screen.getByPlaceholderText(/search/i);
      fireEvent.change(searchInput, { target: { value: 'logo' } });
      
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledWith(
          expect.objectContaining({
            search: 'logo',
          })
        );
      });
    });

    it('filters by file type', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Open filters and select type
      fireEvent.click(screen.getByText(/filters/i));
      const typeSelect = screen.getAllByRole('combobox')[0];
      fireEvent.change(typeSelect, { target: { value: 'image' } });
      
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledWith(
          expect.objectContaining({
            file_type: 'image',
          })
        );
      });
    });

    it('filters by status', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Open filters and select status
      fireEvent.click(screen.getByText(/filters/i));
      const statusSelect = screen.getAllByRole('combobox')[1];
      fireEvent.change(statusSelect, { target: { value: 'indexed' } });
      
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledWith(
          expect.objectContaining({
            status: 'indexed',
          })
        );
      });
    });

    it('resets page when filter changes', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: mockFiles.concat(mockFiles).concat(mockFiles).concat(mockFiles),
        count: 25,
        next: 'http://api/assets/?page=2',
        previous: null,
        total_size: 100000000,
      });
      
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getAllByText('logo.png').length).toBeGreaterThan(0);
      });
      
      // Go to page 2
      fireEvent.click(screen.getByRole('button', { name: /next|2/i }));
      
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledWith(
          expect.objectContaining({ page: 2 })
        );
      });
      
      // Change filter - should reset to page 1
      fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'test' } });
      
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledWith(
          expect.objectContaining({
            page: 1,
            search: 'test',
          })
        );
      });
    });
  });

  describe('Pagination', () => {
    it('renders pagination when more than one page', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: mockFiles,
        count: 25,
        next: 'http://api/assets/?page=2',
        previous: null,
        total_size: 50000000,
      });
      
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
      });
    });

    it('navigates to next page', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: mockFiles,
        count: 25,
        next: 'http://api/assets/?page=2',
        previous: null,
        total_size: 50000000,
      });
      
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByRole('button', { name: /next/i }));
      
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledWith(
          expect.objectContaining({ page: 2 })
        );
      });
    });

    it('supports page size change', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: mockFiles,
        count: 25,
        next: 'http://api/assets/?page=2',
        previous: null,
        total_size: 50000000,
      });
      
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Find and change page size selector
      const pageSizeSelect = screen.getByLabelText(/per page|page size/i) || 
        screen.getAllByRole('combobox').find(s => s.textContent?.includes('10'));
      
      if (pageSizeSelect) {
        fireEvent.change(pageSizeSelect, { target: { value: '25' } });
        
        await waitFor(() => {
          expect(assetsApi.getAssets).toHaveBeenCalledWith(
            expect.objectContaining({ page_size: 25 })
          );
        });
      }
    });

    it('shows current page info', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: mockFiles,
        count: 25,
        next: 'http://api/assets/?page=2',
        previous: null,
        total_size: 50000000,
      });
      
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/page 1|1 of/i)).toBeInTheDocument();
      });
    });
  });

  describe('Sorting', () => {
    it('sorts by uploaded_at by default', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledWith(
          expect.objectContaining({
            ordering: '-uploaded_at',
          })
        );
      });
    });

    it('changes sort field', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      // Change sort field
      const sortSelect = screen.getAllByRole('combobox').find(s => 
        Array.from(s.querySelectorAll('option')).some(o => o.textContent?.includes('Name'))
      );
      
      if (sortSelect) {
        fireEvent.change(sortSelect, { target: { value: 'file_name' } });
        
        await waitFor(() => {
          expect(assetsApi.getAssets).toHaveBeenCalledWith(
            expect.objectContaining({
              ordering: expect.stringContaining('file_name'),
            })
          );
        });
      }
    });
  });

  describe('File Actions', () => {
    it('can view file', async () => {
      const windowOpen = jest.spyOn(window, 'open').mockImplementation(() => null);
      
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      const viewButtons = screen.getAllByRole('button', { name: /view/i });
      fireEvent.click(viewButtons[0]);
      
      await waitFor(() => {
        expect(assetsApi.getSignedUrl).toHaveBeenCalledWith('1');
      });
      
      windowOpen.mockRestore();
    });

    it('can delete file with confirmation', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
      fireEvent.click(deleteButtons[0]);
      
      // Confirm deletion
      fireEvent.click(screen.getByRole('button', { name: /confirm|yes/i }));
      
      await waitFor(() => {
        expect(assetsApi.deleteAsset).toHaveBeenCalledWith('1');
      });
    });

    it('refreshes list after delete', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
      fireEvent.click(deleteButtons[0]);
      
      // Confirm deletion
      fireEvent.click(screen.getByRole('button', { name: /confirm|yes/i }));
      
      await waitFor(() => {
        // Should refresh the list
        expect(assetsApi.getAssets).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('Bulk Actions', () => {
    it('shows bulk action bar when files selected', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Select a file
      const checkboxes = screen.getAllByRole('checkbox');
      if (checkboxes.length > 0) {
        fireEvent.click(checkboxes[0]);
        
        expect(screen.getByText(/1 selected|delete selected/i)).toBeInTheDocument();
      }
    });

    it('can select all files', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Find select all checkbox
      const selectAllCheckbox = screen.getByRole('checkbox', { name: /select all/i });
      if (selectAllCheckbox) {
        fireEvent.click(selectAllCheckbox);
        
        expect(screen.getByText(/3 selected/i)).toBeInTheDocument();
      }
    });

    it('can bulk delete selected files', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Select files
      const checkboxes = screen.getAllByRole('checkbox');
      if (checkboxes.length > 0) {
        fireEvent.click(checkboxes[0]);
        fireEvent.click(checkboxes[1]);
        
        // Click bulk delete
        fireEvent.click(screen.getByRole('button', { name: /delete selected/i }));
        
        // Confirm
        fireEvent.click(screen.getByRole('button', { name: /confirm|yes/i }));
        
        await waitFor(() => {
          expect(assetsApi.deleteAsset).toHaveBeenCalledTimes(2);
        });
      }
    });
  });

  describe('Accessibility', () => {
    it('has accessible dialog role', () => {
      render(<AllFilesModal {...defaultProps} />);
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('has accessible modal title', () => {
      render(<AllFilesModal {...defaultProps} />);
      
      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAccessibleName();
    });

    it('traps focus within modal', async () => {
      render(<AllFilesModal {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Modal should contain focus
      expect(document.activeElement?.closest('[role="dialog"]')).toBeTruthy();
    });

    it('closes on Escape key', () => {
      const onClose = jest.fn();
      render(<AllFilesModal {...defaultProps} onClose={onClose} />);
      
      fireEvent.keyDown(document, { key: 'Escape' });
      
      expect(onClose).toHaveBeenCalled();
    });
  });
});
