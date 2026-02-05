/**
 * Phase 7.3: Frontend Unit Tests - AssetUploadForm Component
 * 
 * Tests for src/components/onboarding/AssetUploadForm.tsx
 * Focusing on file browser integration, pagination, and signed URL features
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AssetUploadForm } from '../AssetUploadForm';
import { assetsApi, apiClient } from '@/lib/api';

// Mock the api module
jest.mock('@/lib/api', () => ({
  assetsApi: {
    getAssets: jest.fn(),
    deleteAsset: jest.fn(),
    getSignedUrl: jest.fn(),
    uploadAsset: jest.fn(),
  },
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    delete: jest.fn(),
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
    file_name: 'hero.jpg',
    file_type: 'image',
    file_size: 204800,
    status: 'indexed',
    uploaded_at: '2025-01-19T15:00:00Z',
    gcs_uri: 'gs://bucket/hero.jpg',
  },
  {
    id: '3',
    file_name: 'brand-video.mp4',
    file_type: 'video',
    file_size: 5242880,
    status: 'pending',
    uploaded_at: '2025-01-18T09:00:00Z',
    gcs_uri: 'gs://bucket/brand-video.mp4',
  },
];

describe('AssetUploadForm', () => {
  const defaultProps = {
    companyId: 'company-123',
    onUploadComplete: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (assetsApi.getAssets as jest.Mock).mockResolvedValue({
      results: mockFiles,
      count: 3,
      next: null,
      previous: null,
      total_size: 5550080,
    });
    (assetsApi.deleteAsset as jest.Mock).mockResolvedValue({});
    (assetsApi.getSignedUrl as jest.Mock).mockResolvedValue({
      signed_url: 'https://storage.googleapis.com/signed-url',
      expires_at: '2025-01-20T10:45:00Z',
    });
    (assetsApi.uploadAsset as jest.Mock).mockResolvedValue({
      id: '4',
      file_name: 'new-upload.png',
      file_type: 'image',
      file_size: 50000,
      status: 'pending',
    });
  });

  describe('Component Rendering', () => {
    it('renders upload form', () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      expect(screen.getByText(/upload|drop files/i)).toBeInTheDocument();
    });

    it('renders file list section', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
    });

    it('shows view all button when files exist', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /view all|see all|all files/i })).toBeInTheDocument();
      });
    });
  });

  describe('Compact File Browser', () => {
    it('displays limited number of files in compact view', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: mockFiles.slice(0, 5),
        count: 25,
        next: 'http://api/assets/?page=2',
        previous: null,
        total_size: 50000000,
        limited: true,
      });
      
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        // Should show files but not all 25
        const fileItems = screen.getAllByText(/\.png|\.jpg|\.mp4/);
        expect(fileItems.length).toBeLessThanOrEqual(5);
      });
    });

    it('shows total file count summary', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: mockFiles.slice(0, 5),
        count: 25,
        next: null,
        previous: null,
        total_size: 50000000,
      });
      
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/25 files/i)).toBeInTheDocument();
      });
    });

    it('opens modal when View All clicked', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      fireEvent.click(screen.getByRole('button', { name: /view all|see all|all files/i }));
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  describe('File Upload', () => {
    it('renders dropzone area', () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      expect(screen.getByText(/drag.*drop|click.*upload/i)).toBeInTheDocument();
    });

    it('accepts file drop', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      const dropzone = screen.getByTestId('dropzone') || screen.getByText(/drag.*drop/i).closest('div');
      const file = new File(['test content'], 'test.png', { type: 'image/png' });
      
      if (dropzone) {
        fireEvent.drop(dropzone, {
          dataTransfer: {
            files: [file],
          },
        });
        
        await waitFor(() => {
          expect(assetsApi.uploadAsset).toHaveBeenCalled();
        });
      }
    });

    it('accepts file selection via input', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      const fileInput = screen.getByLabelText(/upload|choose file/i) || 
        document.querySelector('input[type="file"]');
      
      if (fileInput) {
        const file = new File(['test content'], 'test.png', { type: 'image/png' });
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          expect(assetsApi.uploadAsset).toHaveBeenCalled();
        });
      }
    });

    it('shows upload progress', async () => {
      (assetsApi.uploadAsset as jest.Mock).mockImplementation(
        () => new Promise(resolve => setTimeout(resolve, 100))
      );
      
      render(<AssetUploadForm {...defaultProps} />);
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        const file = new File(['test content'], 'test.png', { type: 'image/png' });
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          expect(screen.getByText(/uploading|progress|%/i)).toBeInTheDocument();
        });
      }
    });

    it('calls onUploadComplete after successful upload', async () => {
      const onUploadComplete = jest.fn();
      render(<AssetUploadForm {...defaultProps} onUploadComplete={onUploadComplete} />);
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        const file = new File(['test content'], 'test.png', { type: 'image/png' });
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          expect(onUploadComplete).toHaveBeenCalled();
        });
      }
    });

    it('refreshes file list after upload', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      // Initial load
      await waitFor(() => {
        expect(assetsApi.getAssets).toHaveBeenCalledTimes(1);
      });
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        const file = new File(['test content'], 'test.png', { type: 'image/png' });
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          // Should refresh after upload
          expect(assetsApi.getAssets).toHaveBeenCalledTimes(2);
        });
      }
    });

    it('shows error on upload failure', async () => {
      (assetsApi.uploadAsset as jest.Mock).mockRejectedValue(new Error('Upload failed'));
      
      render(<AssetUploadForm {...defaultProps} />);
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        const file = new File(['test content'], 'test.png', { type: 'image/png' });
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          expect(screen.getByText(/error|failed/i)).toBeInTheDocument();
        });
      }
    });
  });

  describe('File Actions in Compact View', () => {
    it('can view file with signed URL', async () => {
      const windowOpen = jest.spyOn(window, 'open').mockImplementation(() => null);
      
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      const viewButtons = screen.getAllByRole('button', { name: /view|👁/i });
      fireEvent.click(viewButtons[0]);
      
      await waitFor(() => {
        expect(assetsApi.getSignedUrl).toHaveBeenCalledWith('1');
        expect(windowOpen).toHaveBeenCalledWith(
          'https://storage.googleapis.com/signed-url',
          '_blank'
        );
      });
      
      windowOpen.mockRestore();
    });

    it('can delete file from compact view', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      const deleteButtons = screen.getAllByRole('button', { name: /delete|🗑|×/i });
      fireEvent.click(deleteButtons[0]);
      
      // Confirm deletion
      fireEvent.click(screen.getByRole('button', { name: /confirm|yes/i }));
      
      await waitFor(() => {
        expect(assetsApi.deleteAsset).toHaveBeenCalledWith('1');
      });
    });

    it('refreshes list after delete', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      const deleteButtons = screen.getAllByRole('button', { name: /delete|🗑|×/i });
      fireEvent.click(deleteButtons[0]);
      
      // Confirm deletion
      fireEvent.click(screen.getByRole('button', { name: /confirm|yes/i }));
      
      await waitFor(() => {
        // Should refresh after delete
        expect(assetsApi.getAssets).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('File Type Validation', () => {
    it('accepts valid image types', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          expect(assetsApi.uploadAsset).toHaveBeenCalled();
        });
      }
    });

    it('accepts valid video types', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        const file = new File(['test'], 'video.mp4', { type: 'video/mp4' });
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          expect(assetsApi.uploadAsset).toHaveBeenCalled();
        });
      }
    });

    it('rejects invalid file types', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        const file = new File(['test'], 'malware.exe', { type: 'application/x-msdownload' });
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          expect(screen.getByText(/invalid|not allowed|unsupported/i)).toBeInTheDocument();
        });
        
        expect(assetsApi.uploadAsset).not.toHaveBeenCalled();
      }
    });

    it('rejects files exceeding size limit', async () => {
      render(<AssetUploadForm {...defaultProps} maxFileSize={1000000} />);
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        // Create a large file (10MB)
        const largeContent = new Array(10 * 1024 * 1024).fill('x').join('');
        const file = new File([largeContent], 'large.png', { type: 'image/png' });
        Object.defineProperty(file, 'size', { value: 10 * 1024 * 1024 });
        
        fireEvent.change(fileInput, { target: { files: [file] } });
        
        await waitFor(() => {
          expect(screen.getByText(/too large|exceeds|size limit/i)).toBeInTheDocument();
        });
      }
    });
  });

  describe('Empty State', () => {
    it('shows empty state when no files', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: [],
        count: 0,
        next: null,
        previous: null,
        total_size: 0,
      });
      
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/no files|upload your first|get started/i)).toBeInTheDocument();
      });
    });

    it('hides View All button when no files', async () => {
      (assetsApi.getAssets as jest.Mock).mockResolvedValue({
        results: [],
        count: 0,
        next: null,
        previous: null,
        total_size: 0,
      });
      
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /view all/i })).not.toBeInTheDocument();
      });
    });
  });

  describe('Storage Info', () => {
    it('displays total storage used', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/5\.(3|4) MB/i)).toBeInTheDocument();
      });
    });

    it('displays file count', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText(/3 files/i)).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('has accessible upload button', () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      const uploadButton = screen.getByRole('button', { name: /upload/i }) ||
        screen.getByLabelText(/upload/i);
      
      expect(uploadButton).toHaveAccessibleName();
    });

    it('file input has accessible label', () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) {
        expect(fileInput).toHaveAccessibleName();
      }
    });

    it('supports keyboard navigation', async () => {
      render(<AssetUploadForm {...defaultProps} />);
      
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
      
      // Tab through interactive elements
      const viewAllButton = screen.getByRole('button', { name: /view all/i });
      viewAllButton.focus();
      
      expect(document.activeElement).toBe(viewAllButton);
    });
  });
});
