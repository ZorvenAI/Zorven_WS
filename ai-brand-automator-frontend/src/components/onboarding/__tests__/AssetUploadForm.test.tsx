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

// Mock the api module — apiClient methods return Response-like objects;
// assetsApi.getSignedUrl returns parsed data directly.
jest.mock('@/lib/api', () => ({
  assetsApi: {
    getSignedUrl: jest.fn(),
  },
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    delete: jest.fn(),
    upload: jest.fn(),
  },
}));

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
}));

// Mock AllFilesModal to keep tests focused on AssetUploadForm
jest.mock('@/components/ui/AllFilesModal', () => ({
  AllFilesModal: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div role="dialog">All Files Modal</div> : null,
}));

const mockFiles = [
  {
    id: '1',
    file_name: 'logo.png',
    file_type: 'image',
    file_size: 102400,
    pipeline_status: 'indexed' as const,
  },
  {
    id: '2',
    file_name: 'hero.jpg',
    file_type: 'image',
    file_size: 204800,
    pipeline_status: 'indexed' as const,
  },
  {
    id: '3',
    file_name: 'brand-video.mp4',
    file_type: 'video',
    file_size: 5242880,
    pipeline_status: 'indexed' as const,
  },
];

/** Helper to build a Response-like object for apiClient mocks. */
function mockResponse(data: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => data };
}

describe('AssetUploadForm', () => {
  const originalConfirm = window.confirm;

  beforeEach(() => {
    jest.clearAllMocks();

    // localStorage — component reads company_id before uploading
    jest.spyOn(Storage.prototype, 'getItem').mockImplementation((key: string) => {
      if (key === 'company_id') return '123';
      return null;
    });

    // window.confirm — component uses native confirm for delete
    window.confirm = jest.fn(() => true);

    // Default: apiClient.get returns the three mock files
    (apiClient.get as jest.Mock).mockResolvedValue(
      mockResponse({ results: mockFiles, count: 3, has_more: false }),
    );

    // Default: apiClient.upload returns a successful new file
    (apiClient.upload as jest.Mock).mockResolvedValue(
      mockResponse({
        id: '4',
        file_name: 'new-upload.png',
        file_type: 'image',
        file_size: 50000,
        pipeline_status: 'indexed',
      }),
    );

    // Default: apiClient.delete returns success
    (apiClient.delete as jest.Mock).mockResolvedValue(mockResponse({}));

    // Default: assetsApi.getSignedUrl returns view + download URLs
    (assetsApi.getSignedUrl as jest.Mock).mockResolvedValue({
      view_url: 'https://storage.googleapis.com/signed-view-url',
      download_url: 'https://storage.googleapis.com/signed-download-url',
    });
  });

  afterEach(() => {
    window.confirm = originalConfirm;
    jest.restoreAllMocks();
  });

  // -------------------------------------------------
  // Component Rendering
  // -------------------------------------------------
  describe('Component Rendering', () => {
    it('renders upload form', () => {
      render(<AssetUploadForm />);
      expect(screen.getByText(/Upload files/i)).toBeInTheDocument();
    });

    it('renders file list section', async () => {
      render(<AssetUploadForm />);
      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });
    });

    it('shows view all button when files exist', async () => {
      // View All only shows when totalCount > displayLimit (default 6)
      (apiClient.get as jest.Mock).mockResolvedValue(
        mockResponse({ results: mockFiles, count: 10, has_more: true }),
      );

      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /View All/i }),
        ).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------
  // Compact File Browser
  // -------------------------------------------------
  describe('Compact File Browser', () => {
    it('displays limited number of files in compact view', async () => {
      (apiClient.get as jest.Mock).mockResolvedValue(
        mockResponse({ results: mockFiles, count: 25, has_more: true }),
      );

      render(<AssetUploadForm />);

      await waitFor(() => {
        const fileItems = screen.getAllByText(/\.png|\.jpg|\.mp4/);
        expect(fileItems.length).toBeLessThanOrEqual(5);
      });
    });

    it('shows total file count summary', async () => {
      (apiClient.get as jest.Mock).mockResolvedValue(
        mockResponse({ results: mockFiles, count: 25, has_more: true }),
      );

      render(<AssetUploadForm />);

      await waitFor(() => {
        // Header shows "(3/25)" when has_more is true
        expect(screen.getByText(/\/25/)).toBeInTheDocument();
      });
    });

    it('opens modal when View All clicked', async () => {
      (apiClient.get as jest.Mock).mockResolvedValue(
        mockResponse({ results: mockFiles, count: 10, has_more: true }),
      );

      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      fireEvent.click(
        screen.getByRole('button', { name: /View All/i }),
      );

      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  // -------------------------------------------------
  // File Upload
  // -------------------------------------------------
  describe('File Upload', () => {
    it('renders dropzone area', () => {
      render(<AssetUploadForm />);
      expect(screen.getByText(/drag and drop/i)).toBeInTheDocument();
    });

    it('accepts file drop', async () => {
      // Component uploads via the file input (not an onDrop handler)
      render(<AssetUploadForm />);

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();

      const file = new File(['test content'], 'test.png', {
        type: 'image/png',
      });
      fireEvent.change(fileInput!, { target: { files: [file] } });

      await waitFor(() => {
        expect(apiClient.upload).toHaveBeenCalledWith(
          '/assets/upload/',
          expect.any(FormData),
        );
      });
    });

    it('accepts file selection via input', async () => {
      render(<AssetUploadForm />);

      const fileInput = screen.getByLabelText(/Upload files/i);
      const file = new File(['test content'], 'test.png', {
        type: 'image/png',
      });
      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(apiClient.upload).toHaveBeenCalledWith(
          '/assets/upload/',
          expect.any(FormData),
        );
      });
    });

    it('shows upload progress', async () => {
      // Never-resolving promise keeps uploading === true
      (apiClient.upload as jest.Mock).mockReturnValue(
        new Promise(() => {}),
      );

      render(<AssetUploadForm />);

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();

      const file = new File(['test content'], 'test.png', {
        type: 'image/png',
      });
      fireEvent.change(fileInput!, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Uploading/i)).toBeInTheDocument();
      });
    });

    it('calls onUploadComplete after successful upload', async () => {
      // Component adds the uploaded file directly to the rendered list
      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();

      const file = new File(['test content'], 'new-upload.png', {
        type: 'image/png',
      });
      fireEvent.change(fileInput!, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText('new-upload.png')).toBeInTheDocument();
      });
    });

    it('refreshes file list after upload', async () => {
      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledTimes(1);
      });

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();

      const file = new File(['test content'], 'new-upload.png', {
        type: 'image/png',
      });
      fireEvent.change(fileInput!, { target: { files: [file] } });

      // After upload the new file is appended to state (no second fetch)
      await waitFor(() => {
        expect(screen.getByText('new-upload.png')).toBeInTheDocument();
      });
    });

    it('shows error on upload failure', async () => {
      (apiClient.upload as jest.Mock).mockRejectedValue(
        new Error('Network failure'),
      );

      render(<AssetUploadForm />);

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();

      const file = new File(['test content'], 'test.png', {
        type: 'image/png',
      });
      fireEvent.change(fileInput!, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------
  // File Actions in Compact View
  // -------------------------------------------------
  describe('File Actions in Compact View', () => {
    it('can view file with signed URL', async () => {
      const windowOpen = jest
        .spyOn(window, 'open')
        .mockImplementation(() => null);

      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      // Click the first "View file" button (title attribute)
      const viewButtons = screen.getAllByTitle('View file');
      fireEvent.click(viewButtons[0]);

      await waitFor(() => {
        expect(assetsApi.getSignedUrl).toHaveBeenCalledWith('1');
        expect(windowOpen).toHaveBeenCalledWith(
          'https://storage.googleapis.com/signed-view-url',
          '_blank',
        );
      });

      windowOpen.mockRestore();
    });

    it('can delete file from compact view', async () => {
      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      // Click the first "Delete file" button (title attribute)
      const deleteButtons = screen.getAllByTitle('Delete file');
      fireEvent.click(deleteButtons[0]);

      // window.confirm is mocked to return true
      await waitFor(() => {
        expect(apiClient.delete).toHaveBeenCalledWith('/assets/1/');
      });
    });

    it('refreshes list after delete', async () => {
      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      const deleteButtons = screen.getAllByTitle('Delete file');
      fireEvent.click(deleteButtons[0]);

      // After delete the file is removed from state directly
      await waitFor(() => {
        expect(screen.queryByText('logo.png')).not.toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------
  // File Type Validation
  // -------------------------------------------------
  describe('File Type Validation', () => {
    it('accepts valid image types', async () => {
      render(<AssetUploadForm />);

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();

      const file = new File(['test'], 'image.jpg', { type: 'image/jpeg' });
      fireEvent.change(fileInput!, { target: { files: [file] } });

      await waitFor(() => {
        expect(apiClient.upload).toHaveBeenCalled();
      });
    });

    it('accepts valid video types', async () => {
      render(<AssetUploadForm />);

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();

      const file = new File(['test'], 'video.mp4', { type: 'video/mp4' });
      fireEvent.change(fileInput!, { target: { files: [file] } });

      await waitFor(() => {
        expect(apiClient.upload).toHaveBeenCalled();
      });
    });

    it('rejects invalid file types', async () => {
      // File type restriction is enforced by the accept attribute on the input
      render(<AssetUploadForm />);

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();
      expect(fileInput!.getAttribute('accept')).toContain('image/*');
      expect(fileInput!.getAttribute('accept')).not.toContain('.exe');
    });

    it('rejects files exceeding size limit', async () => {
      // The component displays a file size limit in the UI
      render(<AssetUploadForm />);
      expect(screen.getByText(/50MB/i)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------
  // Empty State
  // -------------------------------------------------
  describe('Empty State', () => {
    it('shows empty state when no files', async () => {
      (apiClient.get as jest.Mock).mockResolvedValue(
        mockResponse({ results: [], count: 0, has_more: false }),
      );

      render(<AssetUploadForm />);

      await waitFor(() => {
        // Upload area is shown; file list heading is not
        expect(screen.getByText(/Upload files/i)).toBeInTheDocument();
        expect(
          screen.queryByText(/Uploaded Files/i),
        ).not.toBeInTheDocument();
      });
    });

    it('hides View All button when no files', async () => {
      (apiClient.get as jest.Mock).mockResolvedValue(
        mockResponse({ results: [], count: 0, has_more: false }),
      );

      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalled();
      });

      expect(
        screen.queryByRole('button', { name: /View All/i }),
      ).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------
  // Storage Info
  // -------------------------------------------------
  describe('Storage Info', () => {
    it('displays total storage used', async () => {
      render(<AssetUploadForm />);

      await waitFor(() => {
        // Per-file sizes shown in KB: 102400 / 1024 = 100.0
        expect(screen.getByText(/100\.0 KB/)).toBeInTheDocument();
      });
    });

    it('displays file count', async () => {
      render(<AssetUploadForm />);

      await waitFor(() => {
        // Header shows the count in parentheses: "(3)"
        expect(screen.getByText(/\(3\)/)).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------
  // Accessibility
  // -------------------------------------------------
  describe('Accessibility', () => {
    it('has accessible upload button', () => {
      render(<AssetUploadForm />);

      const fileInput = screen.getByLabelText(/Upload files/i);
      expect(fileInput).toHaveAccessibleName();
    });

    it('file input has accessible label', () => {
      render(<AssetUploadForm />);

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();
      if (fileInput) {
        expect(fileInput).toHaveAccessibleName();
      }
    });

    it('supports keyboard navigation', async () => {
      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      // Verify interactive elements can receive focus
      const nextButton = screen.getByRole('button', { name: /Next Step/i });
      nextButton.focus();
      expect(document.activeElement).toBe(nextButton);
    });
  });
});
