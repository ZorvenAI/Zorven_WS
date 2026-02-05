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

describe('FileListItem', () => {
  const defaultProps = {
    file: mockFile,
    onDelete: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (assetsApi.getSignedUrl as jest.Mock).mockResolvedValue({
      signed_url: 'https://storage.googleapis.com/signed-url',
      expires_at: '2025-01-20T10:45:00Z',
    });
  });

  describe('File Information Display', () => {
    it('renders file name', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByText('test-image.jpg')).toBeInTheDocument();
    });

    it('renders formatted file size', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByText('1.00 MB')).toBeInTheDocument();
    });

    it('renders small file sizes correctly', () => {
      const smallFile = { ...mockFile, file_size: 500 };
      render(<FileListItem {...defaultProps} file={smallFile} />);
      
      expect(screen.getByText('500 B')).toBeInTheDocument();
    });

    it('renders KB file sizes correctly', () => {
      const kbFile = { ...mockFile, file_size: 5120 };
      render(<FileListItem {...defaultProps} file={kbFile} />);
      
      expect(screen.getByText('5.00 KB')).toBeInTheDocument();
    });

    it('renders file type badge', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByText('image')).toBeInTheDocument();
    });

    it('renders file status', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByText('indexed')).toBeInTheDocument();
    });

    it('renders different status colors', () => {
      const pendingFile = { ...mockFile, pipeline_status: 'pending' as const };
      const { rerender } = render(<FileListItem {...defaultProps} file={pendingFile} />);
      
      expect(screen.getByText('pending')).toBeInTheDocument();

      const failedFile = { ...mockFile, pipeline_status: 'failed' as const };
      rerender(<FileListItem {...defaultProps} file={failedFile} />);
      
      expect(screen.getByText('failed')).toBeInTheDocument();
    });

    it('formats upload date correctly', () => {
      render(<FileListItem {...defaultProps} />);
      
      // Should display relative or absolute date
      expect(screen.getByText(/2025|Jan|ago/i)).toBeInTheDocument();
    });
  });

  describe('File Type Icons', () => {
    it('shows image icon for image files', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByText('🖼️')).toBeInTheDocument();
    });

    it('shows video icon for video files', () => {
      const videoFile = { ...mockFile, file_type: 'video' as const };
      render(<FileListItem {...defaultProps} file={videoFile} />);
      
      expect(screen.getByText('🎬')).toBeInTheDocument();
    });

    it('shows document icon for document files', () => {
      const docFile = { ...mockFile, file_type: 'document' as const };
      render(<FileListItem {...defaultProps} file={docFile} />);
      
      expect(screen.getByText('📄')).toBeInTheDocument();
    });

    it('shows generic icon for other files', () => {
      const otherFile = { ...mockFile, file_type: 'other' as const };
      render(<FileListItem {...defaultProps} file={otherFile} />);
      
      expect(screen.getByText('📁')).toBeInTheDocument();
    });
  });

  describe('View Action', () => {
    it('renders view button', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /view/i })).toBeInTheDocument();
    });

    it('fetches signed URL and opens in new tab on view click', async () => {
      const windowOpen = jest.spyOn(window, 'open').mockImplementation(() => null);
      
      render(<FileListItem {...defaultProps} />);
      
      fireEvent.click(screen.getByRole('button', { name: /view/i }));
      
      await waitFor(() => {
        expect(assetsApi.getSignedUrl).toHaveBeenCalledWith('123');
        expect(windowOpen).toHaveBeenCalledWith(
          'https://storage.googleapis.com/signed-url',
          '_blank'
        );
      });

      windowOpen.mockRestore();
    });

    it('shows loading state during view', async () => {
      (assetsApi.getSignedUrl as jest.Mock).mockImplementation(
        () => new Promise(resolve => setTimeout(resolve, 100))
      );
      
      render(<FileListItem {...defaultProps} />);
      
      fireEvent.click(screen.getByRole('button', { name: /view/i }));
      
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('shows error message on view failure', async () => {
      (assetsApi.getSignedUrl as jest.Mock).mockRejectedValue(new Error('Failed to get URL'));
      
      render(<FileListItem {...defaultProps} />);
      
      fireEvent.click(screen.getByRole('button', { name: /view/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/error|failed/i)).toBeInTheDocument();
      });
    });
  });

  describe('Download Action', () => {
    it('renders download button', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
    });

    it('fetches signed URL and initiates download on click', async () => {
      // Mock creating and clicking an anchor
      const mockClick = jest.fn();
      const mockAnchor = { href: '', download: '', click: mockClick };
      jest.spyOn(document, 'createElement').mockImplementation((tagName) => {
        if (tagName === 'a') return mockAnchor as unknown as HTMLAnchorElement;
        return document.createElement(tagName);
      });
      
      render(<FileListItem {...defaultProps} />);
      
      fireEvent.click(screen.getByRole('button', { name: /download/i }));
      
      await waitFor(() => {
        expect(assetsApi.getSignedUrl).toHaveBeenCalledWith('123');
        expect(mockAnchor.href).toBe('https://storage.googleapis.com/signed-url');
        expect(mockAnchor.download).toBe('test-image.jpg');
        expect(mockClick).toHaveBeenCalled();
      });
    });
  });

  describe('Delete Action', () => {
    it('renders delete button', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
    });

    it('shows confirmation dialog on delete click', () => {
      render(<FileListItem {...defaultProps} />);
      
      fireEvent.click(screen.getByRole('button', { name: /delete/i }));
      
      expect(screen.getByText(/are you sure/i)).toBeInTheDocument();
    });

    it('calls onDelete when confirmed', () => {
      const onDelete = jest.fn();
      render(<FileListItem {...defaultProps} onDelete={onDelete} />);
      
      // Click delete
      fireEvent.click(screen.getByRole('button', { name: /delete/i }));
      
      // Confirm deletion
      fireEvent.click(screen.getByRole('button', { name: /confirm|yes/i }));
      
      expect(onDelete).toHaveBeenCalledWith('123');
    });

    it('cancels deletion on cancel click', () => {
      const onDelete = jest.fn();
      render(<FileListItem {...defaultProps} onDelete={onDelete} />);
      
      // Click delete
      fireEvent.click(screen.getByRole('button', { name: /delete/i }));
      
      // Cancel
      fireEvent.click(screen.getByRole('button', { name: /cancel|no/i }));
      
      expect(onDelete).not.toHaveBeenCalled();
      expect(screen.queryByText(/are you sure/i)).not.toBeInTheDocument();
    });
  });

  describe('Compact Mode', () => {
    it('renders in compact mode when specified', () => {
      render(<FileListItem {...defaultProps} compact={true} />);
      
      expect(screen.getByText('test-image.jpg')).toBeInTheDocument();
    });

    it('renders in normal mode by default', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByText('test-image.jpg')).toBeInTheDocument();
      expect(screen.getByText('image')).toBeInTheDocument();
      expect(screen.getByText('indexed')).toBeInTheDocument();
      expect(screen.getByText('1.0 MB')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has accessible button labels', () => {
      render(<FileListItem {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /view/i })).toHaveAccessibleName();
      expect(screen.getByRole('button', { name: /download/i })).toHaveAccessibleName();
      expect(screen.getByRole('button', { name: /delete/i })).toHaveAccessibleName();
    });

    it('displays file info accessibly', () => {
      render(<FileListItem {...defaultProps} />);
      
      const container = screen.getByRole('listitem') || screen.getByRole('row');
      expect(container).toBeInTheDocument();
    });
  });
});
