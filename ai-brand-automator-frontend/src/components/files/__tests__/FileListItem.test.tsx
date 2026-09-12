/**
 * Phase 7.3: Frontend Unit Tests - FileListItem Component
 *
 * Tests for src/components/files/FileListItem.tsx
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FileListItem } from '../FileListItem';
import { AssetFile } from '@/lib/api';

// Mock the api module
jest.mock('@/lib/api', () => ({
  assetsApi: {
    getSignedUrl: jest.fn(),
    deleteAsset: jest.fn(),
  },
}));

import { assetsApi } from '@/lib/api';

const mockFile: AssetFile = {
  id: '123',
  file_name: 'test-image.jpg',
  file_type: 'image',
  file_size: 1048576, // 1MB
  pipeline_status: 'indexed',
  uploaded_at: '2025-01-20T10:30:00Z',
  gcs_path: 'gs://bucket/path/test-image.jpg',
};

// Helper to wrap <tr> in a proper table structure for valid HTML
function renderInTable(ui: React.ReactElement) {
  return render(
    <table>
      <tbody>{ui}</tbody>
    </table>
  );
}

describe('FileListItem', () => {
  const defaultProps = {
    file: mockFile,
    onDelete: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.restoreAllMocks();
    (assetsApi.getSignedUrl as jest.Mock).mockResolvedValue({
      view_url: 'https://storage.googleapis.com/view-url',
      download_url: 'https://storage.googleapis.com/download-url',
      expires_at: '2025-01-20T10:45:00Z',
      file_name: 'test-image.jpg',
      file_type: 'image',
      file_size: 1048576,
    });
    (assetsApi.deleteAsset as jest.Mock).mockResolvedValue(undefined);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('File Information Display', () => {
    it('renders file name', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      expect(screen.getByText('test-image.jpg')).toBeInTheDocument();
    });

    it('renders formatted file size', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      // Component uses .toFixed(1), producing "1.0 MB"
      expect(screen.getByText('1.0 MB')).toBeInTheDocument();
    });

    it('renders small file sizes correctly', () => {
      const smallFile = { ...mockFile, file_size: 500 };
      renderInTable(<FileListItem {...defaultProps} file={smallFile} />);

      expect(screen.getByText('500 B')).toBeInTheDocument();
    });

    it('renders KB file sizes correctly', () => {
      const kbFile = { ...mockFile, file_size: 5120 };
      renderInTable(<FileListItem {...defaultProps} file={kbFile} />);

      // Component uses .toFixed(1), producing "5.0 KB"
      expect(screen.getByText('5.0 KB')).toBeInTheDocument();
    });

    it('renders file type badge', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      expect(screen.getByText('image')).toBeInTheDocument();
    });

    it('renders file status', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      // Status uses getPipelineStatusConfig which capitalizes: "Indexed"
      expect(screen.getByText(/Indexed/)).toBeInTheDocument();
    });

    it('renders different status colors', () => {
      const pendingFile = { ...mockFile, pipeline_status: 'pending' as const };
      const { unmount } = renderInTable(<FileListItem {...defaultProps} file={pendingFile} />);

      // Status label is capitalized via getPipelineStatusConfig
      expect(screen.getByText(/Pending/)).toBeInTheDocument();
      unmount();

      const failedFile = { ...mockFile, pipeline_status: 'failed' as const };
      renderInTable(<FileListItem {...defaultProps} file={failedFile} />);

      expect(screen.getByText(/Failed/)).toBeInTheDocument();
    });

    it('formats upload date correctly', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      // Should display formatted date
      expect(screen.getByText(/2025|Jan|ago/i)).toBeInTheDocument();
    });
  });

  describe('File Type Icons', () => {
    it('shows image icon for image files', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      const iconSpans = screen.getAllByText((_content, element) =>
        element?.textContent?.includes('\u{1F5BC}') ?? false
      );
      expect(iconSpans.length).toBeGreaterThan(0);
    });

    it('shows video icon for video files', () => {
      const videoFile = { ...mockFile, file_type: 'video' as const };
      renderInTable(<FileListItem {...defaultProps} file={videoFile} />);

      const iconSpans = screen.getAllByText((_content, element) =>
        element?.textContent?.includes('\u{1F3AC}') ?? false
      );
      expect(iconSpans.length).toBeGreaterThan(0);
    });

    it('shows document icon for document files', () => {
      const docFile = { ...mockFile, file_type: 'document' as const };
      renderInTable(<FileListItem {...defaultProps} file={docFile} />);

      const iconSpans = screen.getAllByText((_content, element) =>
        element?.textContent?.includes('\u{1F4C4}') ?? false
      );
      expect(iconSpans.length).toBeGreaterThan(0);
    });

    it('shows generic icon for other files', () => {
      const otherFile = { ...mockFile, file_type: 'other' as const };
      renderInTable(<FileListItem {...defaultProps} file={otherFile} />);

      const iconSpans = screen.getAllByText((_content, element) =>
        element?.textContent?.includes('\u{1F4C1}') ?? false
      );
      expect(iconSpans.length).toBeGreaterThan(0);
    });
  });

  describe('View Action', () => {
    it('renders view button', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      // Button has title="View file"
      expect(screen.getByTitle('View file')).toBeInTheDocument();
    });

    it('fetches signed URL and opens in new tab on view click', async () => {
      const windowOpen = jest.spyOn(window, 'open').mockImplementation(() => null);

      renderInTable(<FileListItem {...defaultProps} />);

      fireEvent.click(screen.getByTitle('View file'));

      await waitFor(() => {
        expect(assetsApi.getSignedUrl).toHaveBeenCalledWith('123');
        expect(windowOpen).toHaveBeenCalledWith(
          'https://storage.googleapis.com/view-url',
          '_blank'
        );
      });

      windowOpen.mockRestore();
    });

    it('shows loading state during view', async () => {
      (assetsApi.getSignedUrl as jest.Mock).mockImplementation(
        () => new Promise(resolve => setTimeout(resolve, 200))
      );

      renderInTable(<FileListItem {...defaultProps} />);

      fireEvent.click(screen.getByTitle('View file'));

      // Component disables the button during loading and shows hourglass
      await waitFor(() => {
        const viewButton = screen.getByTitle('View file');
        expect(viewButton).toBeDisabled();
      });
    });

    it('shows error message on view failure', async () => {
      (assetsApi.getSignedUrl as jest.Mock).mockRejectedValue(new Error('Failed to get URL'));

      renderInTable(<FileListItem {...defaultProps} />);

      fireEvent.click(screen.getByTitle('View file'));

      await waitFor(() => {
        expect(screen.getByText(/failed/i)).toBeInTheDocument();
      });
    });
  });

  describe('Download Action', () => {
    it('renders download button', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      // Button has title="Download file"
      expect(screen.getByTitle('Download file')).toBeInTheDocument();
    });

    it('fetches signed URL on download click', async () => {
      renderInTable(<FileListItem {...defaultProps} />);

      fireEvent.click(screen.getByTitle('Download file'));

      await waitFor(() => {
        expect(assetsApi.getSignedUrl).toHaveBeenCalledWith('123');
      });
    });
  });

  describe('Delete Action', () => {
    it('renders delete button', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      // Button has title="Delete file"
      expect(screen.getByTitle('Delete file')).toBeInTheDocument();
    });

    it('calls onDelete when user confirms deletion', async () => {
      // Component uses window.confirm() for confirmation
      jest.spyOn(window, 'confirm').mockReturnValue(true);
      const onDelete = jest.fn().mockResolvedValue(undefined);
      renderInTable(<FileListItem {...defaultProps} onDelete={onDelete} />);

      fireEvent.click(screen.getByTitle('Delete file'));

      await waitFor(() => {
        expect(window.confirm).toHaveBeenCalled();
        // onDelete receives the full file object
        expect(onDelete).toHaveBeenCalledWith(mockFile);
      });
    });

    it('does not call onDelete when user cancels', () => {
      // Component uses window.confirm() - returning false cancels
      jest.spyOn(window, 'confirm').mockReturnValue(false);
      const onDelete = jest.fn();
      renderInTable(<FileListItem {...defaultProps} onDelete={onDelete} />);

      fireEvent.click(screen.getByTitle('Delete file'));

      expect(window.confirm).toHaveBeenCalled();
      expect(onDelete).not.toHaveBeenCalled();
    });

    it('falls back to assetsApi.deleteAsset when no onDelete prop', async () => {
      jest.spyOn(window, 'confirm').mockReturnValue(true);
      renderInTable(<FileListItem file={mockFile} />);

      fireEvent.click(screen.getByTitle('Delete file'));

      await waitFor(() => {
        expect(assetsApi.deleteAsset).toHaveBeenCalledWith('123');
      });
    });
  });

  describe('Compact Mode', () => {
    it('renders in compact mode when specified', () => {
      // Compact mode renders a <div>, not <tr>, so no table wrapper needed
      render(<FileListItem {...defaultProps} compact={true} />);

      expect(screen.getByText('test-image.jpg')).toBeInTheDocument();
    });

    it('renders in normal mode by default', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      expect(screen.getByText('test-image.jpg')).toBeInTheDocument();
      expect(screen.getByText('image')).toBeInTheDocument();
      // Status label is capitalized via getPipelineStatusConfig
      expect(screen.getByText(/Indexed/)).toBeInTheDocument();
      expect(screen.getByText('1.0 MB')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has accessible button titles', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      // Buttons use title attribute for accessibility
      expect(screen.getByTitle('View file')).toBeInTheDocument();
      expect(screen.getByTitle('Download file')).toBeInTheDocument();
      expect(screen.getByTitle('Delete file')).toBeInTheDocument();
    });

    it('displays file info in a table row', () => {
      renderInTable(<FileListItem {...defaultProps} />);

      // Default (non-compact) render produces a <tr> with role="row"
      const row = screen.getByRole('row');
      expect(row).toBeInTheDocument();
    });
  });
});
