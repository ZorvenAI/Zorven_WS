/**
 * Phase 7.3: Frontend Unit Tests - FileFiltersBar Component
 * 
 * Tests for src/components/ui/FileFiltersBar.tsx
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FileFiltersBar } from '../FileFiltersBar';

describe('FileFiltersBar', () => {
  const defaultProps = {
    onSearchChange: jest.fn(),
    onFileTypeChange: jest.fn(),
    onStatusChange: jest.fn(),
    onSortChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('Search Input', () => {
    it('renders search input', () => {
      render(<FileFiltersBar {...defaultProps} />);
      
      expect(screen.getByPlaceholderText(/search files/i)).toBeInTheDocument();
    });

    it('debounces search input (300ms delay)', async () => {
      jest.useRealTimers();
      const onSearchChange = jest.fn();
      render(<FileFiltersBar {...defaultProps} onSearchChange={onSearchChange} />);
      
      const searchInput = screen.getByPlaceholderText(/search files/i);
      fireEvent.change(searchInput, { target: { value: 'test' } });
      
      // Should not be called immediately
      expect(onSearchChange).not.toHaveBeenCalled();
      
      // Wait for debounce
      await waitFor(() => {
        expect(onSearchChange).toHaveBeenCalledWith('test');
      }, { timeout: 500 });
    });

    it('shows clear button when search has text', () => {
      render(<FileFiltersBar {...defaultProps} initialSearch="test" />);
      
      expect(screen.getByRole('button', { name: /✕/i })).toBeInTheDocument();
    });

    it('clears search on clear button click', () => {
      const onSearchChange = jest.fn();
      render(<FileFiltersBar {...defaultProps} onSearchChange={onSearchChange} initialSearch="test" />);
      
      const clearButton = screen.getByRole('button', { name: /✕/i });
      fireEvent.click(clearButton);
      
      expect(onSearchChange).toHaveBeenCalledWith('');
    });
  });

  describe('File Type Dropdown', () => {
    it('renders file type dropdown in advanced filters', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      expect(screen.getByText(/type:/i)).toBeInTheDocument();
    });

    it('has correct file type options', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      const typeSelect = screen.getByLabelText(/type:/i) || screen.getAllByRole('combobox')[0];
      
      expect(typeSelect).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /all/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /image/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /video/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /document/i })).toBeInTheDocument();
    });

    it('calls onFileTypeChange when filter changes', () => {
      const onFileTypeChange = jest.fn();
      render(<FileFiltersBar {...defaultProps} onFileTypeChange={onFileTypeChange} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      const typeSelect = screen.getAllByRole('combobox')[0];
      fireEvent.change(typeSelect, { target: { value: 'image' } });
      
      expect(onFileTypeChange).toHaveBeenCalledWith('image');
    });
  });

  describe('Status Dropdown', () => {
    it('renders status dropdown in advanced filters', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      expect(screen.getByText(/status:/i)).toBeInTheDocument();
    });

    it('has correct status options', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      expect(screen.getByRole('option', { name: /pending/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /indexed/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /failed/i })).toBeInTheDocument();
    });

    it('calls onStatusChange when filter changes', () => {
      const onStatusChange = jest.fn();
      render(<FileFiltersBar {...defaultProps} onStatusChange={onStatusChange} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      const statusSelect = screen.getAllByRole('combobox')[1];
      fireEvent.change(statusSelect, { target: { value: 'indexed' } });
      
      expect(onStatusChange).toHaveBeenCalledWith('indexed');
    });
  });

  describe('Sort Controls', () => {
    it('renders sort dropdown in advanced filters', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      expect(screen.getByText(/sort:/i)).toBeInTheDocument();
    });

    it('has correct sort options', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      expect(screen.getByRole('option', { name: /upload date/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /file name/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /file size/i })).toBeInTheDocument();
    });

    it('calls onSortChange when sort field changes', () => {
      const onSortChange = jest.fn();
      render(<FileFiltersBar {...defaultProps} onSortChange={onSortChange} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      const sortSelect = screen.getAllByRole('combobox')[2];
      fireEvent.change(sortSelect, { target: { value: 'file_name' } });
      
      expect(onSortChange).toHaveBeenCalledWith('file_name', 'desc');
    });

    it('toggles sort order when order button clicked', () => {
      const onSortChange = jest.fn();
      render(<FileFiltersBar {...defaultProps} onSortChange={onSortChange} showFilters={true} />);
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      // Find and click sort order toggle (↓ or ↑)
      const orderButton = screen.getByRole('button', { name: /↓|↑/ });
      fireEvent.click(orderButton);
      
      expect(onSortChange).toHaveBeenCalledWith('uploaded_at', 'asc');
    });
  });

  describe('Clear Filters', () => {
    it('shows clear all button when filters are active', () => {
      render(
        <FileFiltersBar
          {...defaultProps}
          showFilters={true}
          initialSearch="test"
        />
      );
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      expect(screen.getByRole('button', { name: /clear all/i })).toBeInTheDocument();
    });

    it('clears all filters when clear all is clicked', () => {
      const onSearchChange = jest.fn();
      const onFileTypeChange = jest.fn();
      const onStatusChange = jest.fn();
      const onSortChange = jest.fn();

      render(
        <FileFiltersBar
          onSearchChange={onSearchChange}
          onFileTypeChange={onFileTypeChange}
          onStatusChange={onStatusChange}
          onSortChange={onSortChange}
          showFilters={true}
          initialSearch="test"
        />
      );
      
      // Open filters
      fireEvent.click(screen.getByText(/filters/i));
      
      fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
      
      expect(onSearchChange).toHaveBeenCalledWith('');
      expect(onFileTypeChange).toHaveBeenCalledWith('');
      expect(onStatusChange).toHaveBeenCalledWith('');
      expect(onSortChange).toHaveBeenCalledWith('uploaded_at', 'desc');
    });
  });

  describe('Filters Toggle', () => {
    it('shows filters button when showFilters is true', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={true} />);
      
      expect(screen.getByText(/filters/i)).toBeInTheDocument();
    });

    it('hides filters button when showFilters is false', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={false} />);
      
      expect(screen.queryByText(/⚙️ Filters/)).not.toBeInTheDocument();
    });

    it('expands advanced filters on toggle click', () => {
      render(<FileFiltersBar {...defaultProps} showFilters={true} />);
      
      // Initially hidden
      expect(screen.queryByText(/type:/i)).not.toBeInTheDocument();
      
      // Click to expand
      fireEvent.click(screen.getByText(/filters/i));
      
      // Now visible
      expect(screen.getByText(/type:/i)).toBeInTheDocument();
    });
  });
});
