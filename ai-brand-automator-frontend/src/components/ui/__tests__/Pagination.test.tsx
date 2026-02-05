/**
 * Phase 7.3: Frontend Unit Tests - Pagination Component
 * 
 * Tests for src/components/ui/Pagination.tsx
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { Pagination } from '../Pagination';

describe('Pagination', () => {
  const defaultProps = {
    currentPage: 1,
    totalPages: 5,
    hasNext: true,
    hasPrevious: false,
    onPageChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders page info correctly', () => {
      render(<Pagination {...defaultProps} totalCount={45} />);
      
      expect(screen.getByText(/page 1 of 5/i)).toBeInTheDocument();
      expect(screen.getByText(/45 total/i)).toBeInTheDocument();
    });

    it('renders correct number of page buttons', () => {
      render(<Pagination {...defaultProps} />);
      
      // Should show pages 1-5 when totalPages is 5
      for (let i = 1; i <= 5; i++) {
        expect(screen.getByRole('button', { name: String(i) })).toBeInTheDocument();
      }
    });

    it('highlights current page', () => {
      render(<Pagination {...defaultProps} currentPage={3} />);
      
      const currentButton = screen.getByRole('button', { name: '3' });
      expect(currentButton).toHaveClass('bg-brand-electric');
    });

    it('disables prev button on first page', () => {
      render(<Pagination {...defaultProps} currentPage={1} hasPrevious={false} />);
      
      const prevButton = screen.getByRole('button', { name: /prev/i });
      expect(prevButton).toBeDisabled();
    });

    it('disables next button on last page', () => {
      render(<Pagination {...defaultProps} currentPage={5} hasNext={false} />);
      
      const nextButton = screen.getByRole('button', { name: /next/i });
      expect(nextButton).toBeDisabled();
    });

    it('handles single page (no navigation needed)', () => {
      render(
        <Pagination
          {...defaultProps}
          currentPage={1}
          totalPages={1}
          hasNext={false}
          hasPrevious={false}
        />
      );
      
      const prevButton = screen.getByRole('button', { name: /prev/i });
      const nextButton = screen.getByRole('button', { name: /next/i });
      
      expect(prevButton).toBeDisabled();
      expect(nextButton).toBeDisabled();
    });
  });

  describe('Page Size Selector', () => {
    it('renders page size selector when showPageSize is true', () => {
      const onPageSizeChange = jest.fn();
      render(
        <Pagination
          {...defaultProps}
          showPageSize={true}
          onPageSizeChange={onPageSizeChange}
          pageSize={10}
        />
      );
      
      expect(screen.getByText(/per page/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue('10')).toBeInTheDocument();
    });

    it('calls onPageSizeChange when size changes', () => {
      const onPageSizeChange = jest.fn();
      render(
        <Pagination
          {...defaultProps}
          showPageSize={true}
          onPageSizeChange={onPageSizeChange}
          pageSize={10}
        />
      );
      
      const select = screen.getByDisplayValue('10');
      fireEvent.change(select, { target: { value: '25' } });
      
      expect(onPageSizeChange).toHaveBeenCalledWith(25);
    });
  });

  describe('Navigation', () => {
    it('calls onPageChange when clicking page button', () => {
      const onPageChange = jest.fn();
      render(<Pagination {...defaultProps} onPageChange={onPageChange} />);
      
      fireEvent.click(screen.getByRole('button', { name: '3' }));
      
      expect(onPageChange).toHaveBeenCalledWith(3);
    });

    it('calls onPageChange with next page on next click', () => {
      const onPageChange = jest.fn();
      render(
        <Pagination
          {...defaultProps}
          currentPage={2}
          hasPrevious={true}
          onPageChange={onPageChange}
        />
      );
      
      fireEvent.click(screen.getByRole('button', { name: /next/i }));
      
      expect(onPageChange).toHaveBeenCalledWith(3);
    });

    it('calls onPageChange with previous page on prev click', () => {
      const onPageChange = jest.fn();
      render(
        <Pagination
          {...defaultProps}
          currentPage={3}
          hasPrevious={true}
          onPageChange={onPageChange}
        />
      );
      
      fireEvent.click(screen.getByRole('button', { name: /prev/i }));
      
      expect(onPageChange).toHaveBeenCalledWith(2);
    });

    it('navigates to first page on first button click', () => {
      const onPageChange = jest.fn();
      render(
        <Pagination
          {...defaultProps}
          currentPage={3}
          hasPrevious={true}
          onPageChange={onPageChange}
        />
      );
      
      // First page button (⏮)
      const firstButton = screen.getByTitle(/first page/i);
      fireEvent.click(firstButton);
      
      expect(onPageChange).toHaveBeenCalledWith(1);
    });

    it('navigates to last page on last button click', () => {
      const onPageChange = jest.fn();
      render(
        <Pagination
          {...defaultProps}
          currentPage={2}
          hasNext={true}
          totalPages={5}
          onPageChange={onPageChange}
        />
      );
      
      // Last page button (⏭)
      const lastButton = screen.getByTitle(/last page/i);
      fireEvent.click(lastButton);
      
      expect(onPageChange).toHaveBeenCalledWith(5);
    });
  });

  describe('Ellipsis for many pages', () => {
    it('shows ellipsis when there are many pages', () => {
      render(
        <Pagination
          {...defaultProps}
          currentPage={5}
          totalPages={10}
          hasPrevious={true}
          hasNext={true}
        />
      );
      
      // Should show ellipsis between page ranges
      expect(screen.getAllByText('...')).toHaveLength(2); // Start and end ellipsis
    });

    it('shows first page with ellipsis when in middle', () => {
      render(
        <Pagination
          {...defaultProps}
          currentPage={5}
          totalPages={10}
          hasPrevious={true}
          hasNext={true}
        />
      );
      
      // Page 1 should always be visible
      expect(screen.getByRole('button', { name: '1' })).toBeInTheDocument();
      // Page 10 should always be visible
      expect(screen.getByRole('button', { name: '10' })).toBeInTheDocument();
    });
  });
});
