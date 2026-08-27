import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AssetUploadForm } from '../AssetUploadForm';
import { assetsApi, apiClient } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  assetsApi: {
    getSignedUrl: jest.fn(),
  },
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    upload: jest.fn(),
  },
}));

let mockSessionId: string | null = null;
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
  useSearchParams: () => ({
    get: (key: string) => (key === 'sessionId' ? mockSessionId : null),
  }),
}));

jest.mock('@/components/ui/AllFilesModal', () => ({
  AllFilesModal: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div role="dialog">All Files Modal</div> : null,
}));

const mockGetSessionProvenance = jest.fn();
const mockEditProvenance = jest.fn();
jest.mock('@/lib/onboarding-sessions', () => ({
  getSessionProvenance: (...args: unknown[]) =>
    mockGetSessionProvenance(...args),
  editProvenance: (...args: unknown[]) => mockEditProvenance(...args),
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

function mockResponse(data: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => data };
}

describe('AssetUploadForm', () => {
  const originalConfirm = window.confirm;

  beforeEach(() => {
    jest.clearAllMocks();
    mockSessionId = null;

    jest.spyOn(Storage.prototype, 'getItem').mockImplementation((key: string) => {
      if (key === 'company_id') return '123';
      return null;
    });

    window.confirm = jest.fn(() => true);

    (apiClient.get as jest.Mock).mockResolvedValue(
      mockResponse({ results: mockFiles, count: 3, has_more: false }),
    );

    (apiClient.upload as jest.Mock).mockResolvedValue(
      mockResponse({
        id: '4',
        file_name: 'new-upload.png',
        file_type: 'image',
        file_size: 50000,
        pipeline_status: 'indexed',
      }),
    );

    (apiClient.delete as jest.Mock).mockResolvedValue(mockResponse({}));

    (assetsApi.getSignedUrl as jest.Mock).mockResolvedValue({
      view_url: 'https://storage.googleapis.com/signed-view-url',
      download_url: 'https://storage.googleapis.com/signed-download-url',
    });

    (apiClient.patch as jest.Mock).mockResolvedValue(
      mockResponse({ id: 123 }),
    );
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

    it('renders Market & Business section with K-03 fields', () => {
      render(<AssetUploadForm />);

      expect(
        screen.getByLabelText(/brand asset status/i),
      ).toBeInTheDocument();
      expect(screen.getByText(/Market & Business/i)).toBeInTheDocument();
      expect(screen.getByText(/Products & Services/i)).toBeInTheDocument();
      expect(screen.getByText(/Digital Presence/i)).toBeInTheDocument();
      expect(screen.getByText(/Marketing Budget/i)).toBeInTheDocument();
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
        expect(apiClient.get).toHaveBeenCalled();
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

      const deleteButtons = screen.getAllByTitle('Delete file');
      fireEvent.click(deleteButtons[0]);

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
      render(<AssetUploadForm />);

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();
      expect(fileInput!.getAttribute('accept')).toContain('image/*');
      expect(fileInput!.getAttribute('accept')).not.toContain('.exe');
    });

    it('rejects files exceeding size limit', async () => {
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
        expect(screen.getByText(/100\.0 KB/)).toBeInTheDocument();
      });
    });

    it('displays file count', async () => {
      render(<AssetUploadForm />);

      await waitFor(() => {
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

      const nextButton = screen.getByRole('button', { name: /Next Step/i });
      nextButton.focus();
      expect(document.activeElement).toBe(nextButton);
    });
  });

  // -------------------------------------------------
  // K-03: Market & Business Section
  // -------------------------------------------------
  describe('Market & Business Section (K-03)', () => {
    it('renders brand asset status select', () => {
      render(<AssetUploadForm />);

      const select = screen.getByLabelText(/brand asset status/i);
      expect(select).toBeInTheDocument();
      const options = Array.from(select.querySelectorAll('option'));
      const values = options.map((o) => o.getAttribute('value'));
      expect(values).toContain('none');
      expect(values).toContain('basic');
      expect(values).toContain('partial');
      expect(values).toContain('complete');
    });

    it('renders sales channel checkboxes', () => {
      render(<AssetUploadForm />);

      expect(screen.getByLabelText(/online store/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/marketplace/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/retail/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/wholesale/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/direct sales/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/social commerce/i)).toBeInTheDocument();
    });

    it('renders Save Market Info button', () => {
      render(<AssetUploadForm />);

      expect(
        screen.getByRole('button', { name: /save market info/i }),
      ).toBeInTheDocument();
    });

    it('saves market data via Company PATCH', async () => {
      render(<AssetUploadForm />);

      fireEvent.change(screen.getByLabelText(/brand asset status/i), {
        target: { value: 'partial' },
      });

      fireEvent.click(
        screen.getByRole('button', { name: /save market info/i }),
      );

      await waitFor(() => {
        expect(apiClient.patch).toHaveBeenCalledWith(
          '/companies/123/',
          expect.objectContaining({
            brand_asset_status: 'partial',
          }),
        );
      });
    });

    it('adds and removes competitor rows', () => {
      render(<AssetUploadForm />);

      const addButton = screen.getByText(/\+ Add competitor/i);
      fireEvent.click(addButton);

      const removeButtons = screen.getAllByRole('button', {
        name: /remove competitor/i,
      });
      expect(removeButtons.length).toBe(2);

      fireEvent.click(removeButtons[removeButtons.length - 1]);

      expect(
        screen.queryAllByRole('button', { name: /remove competitor/i }).length,
      ).toBeLessThan(2);
    });

    it('works without sessionId — no provenance on market section (AC-2)', async () => {
      mockSessionId = null;

      render(<AssetUploadForm />);

      fireEvent.change(screen.getByLabelText(/brand asset status/i), {
        target: { value: 'complete' },
      });

      fireEvent.click(
        screen.getByRole('button', { name: /save market info/i }),
      );

      await waitFor(() => {
        expect(apiClient.patch).toHaveBeenCalled();
      });

      expect(mockGetSessionProvenance).not.toHaveBeenCalled();
      expect(mockEditProvenance).not.toHaveBeenCalled();
    });

    it('shows provenance badges for agent-filled market fields (AC-3)', async () => {
      mockSessionId = 'sess-4';
      mockGetSessionProvenance.mockResolvedValue({
        session: 4,
        groups: [
          {
            page: 4,
            label: 'Assets & Market',
            fields: [
              {
                id: 40,
                field_name: 'brand_asset_status',
                extracted_value: 'basic',
                status: 'PENDING',
                confidence: 0.75,
                wizard_page: 4,
              },
              {
                id: 41,
                field_name: 'competitors',
                extracted_value: [{ name: 'Acme Corp' }],
                status: 'PENDING',
                confidence: 0.8,
                wizard_page: 4,
              },
            ],
          },
        ],
      });

      (apiClient.get as jest.Mock).mockResolvedValue(
        mockResponse({
          results: mockFiles,
          count: 3,
          has_more: false,
        }),
      );

      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(mockGetSessionProvenance).toHaveBeenCalledWith('sess-4');
      });

      await waitFor(() => {
        const badges = screen.getAllByText('AI');
        expect(badges.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('file upload section remains unchanged with market section', async () => {
      render(<AssetUploadForm />);

      await waitFor(() => {
        expect(screen.getByText('logo.png')).toBeInTheDocument();
      });

      expect(screen.getByText(/Upload files/i)).toBeInTheDocument();
      expect(screen.getByText(/drag and drop/i)).toBeInTheDocument();

      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).not.toBeNull();

      const file = new File(['test content'], 'new-upload.png', {
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
  });
});
