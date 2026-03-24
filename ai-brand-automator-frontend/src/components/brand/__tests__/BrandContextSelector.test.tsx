import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import BrandContextSelector from '../BrandContextSelector';

// Mock useBrandContext hook
const mockSwitchBrand = jest.fn();
let mockBrandContext = {
  brands: [] as Array<{
    brand_context_id: string;
    name: string;
    brand_scope: string;
    parent_brand: string;
    relationship_to_parent: string;
    target_persona: string | null;
  }>,
  activeBrand: null as null | {
    brand_context_id: string;
    name: string;
    brand_scope: string;
  },
  switchBrand: mockSwitchBrand,
  isLoading: false,
  hasSubBrands: false,
  refreshBrands: jest.fn(),
};

jest.mock('@/hooks/useBrandContext', () => ({
  useBrandContext: () => mockBrandContext,
}));

describe('BrandContextSelector', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockBrandContext = {
      brands: [],
      activeBrand: null,
      switchBrand: mockSwitchBrand,
      isLoading: false,
      hasSubBrands: false,
      refreshBrands: jest.fn(),
    };
  });

  it('renders nothing when only parent brand exists', () => {
    mockBrandContext.hasSubBrands = false;
    const { container } = render(<BrandContextSelector />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dropdown when sub-brands exist', () => {
    mockBrandContext.hasSubBrands = true;
    mockBrandContext.activeBrand = {
      brand_context_id: 'parent',
      name: 'Acme Corp',
      brand_scope: 'parent',
    };
    mockBrandContext.brands = [
      {
        brand_context_id: 'parent',
        name: 'Acme Corp',
        brand_scope: 'parent',
        parent_brand: 'Acme Corp',
        relationship_to_parent: 'root',
        target_persona: null,
      },
      {
        brand_context_id: 'sub_brand:acme-pro',
        name: 'Acme Pro',
        brand_scope: 'sub_brand',
        parent_brand: 'Acme Corp',
        relationship_to_parent: 'branded_house',
        target_persona: 'Enterprise IT',
      },
    ];

    render(<BrandContextSelector />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });

  it('opens dropdown on click and shows all brands', () => {
    mockBrandContext.hasSubBrands = true;
    mockBrandContext.activeBrand = {
      brand_context_id: 'parent',
      name: 'Acme Corp',
      brand_scope: 'parent',
    };
    mockBrandContext.brands = [
      {
        brand_context_id: 'parent',
        name: 'Acme Corp',
        brand_scope: 'parent',
        parent_brand: 'Acme Corp',
        relationship_to_parent: 'root',
        target_persona: null,
      },
      {
        brand_context_id: 'sub_brand:acme-pro',
        name: 'Acme Pro',
        brand_scope: 'sub_brand',
        parent_brand: 'Acme Corp',
        relationship_to_parent: 'branded_house',
        target_persona: 'Enterprise IT',
      },
    ];

    render(<BrandContextSelector />);

    // Click to open dropdown
    fireEvent.click(screen.getByText('Acme Corp'));

    // Both brands should be visible in dropdown
    expect(screen.getByText('Acme Pro')).toBeInTheDocument();
    expect(screen.getByText('Sub-Brand')).toBeInTheDocument();
  });

  it('calls switchBrand when selecting a brand', () => {
    mockBrandContext.hasSubBrands = true;
    mockBrandContext.activeBrand = {
      brand_context_id: 'parent',
      name: 'Acme Corp',
      brand_scope: 'parent',
    };
    mockBrandContext.brands = [
      {
        brand_context_id: 'parent',
        name: 'Acme Corp',
        brand_scope: 'parent',
        parent_brand: 'Acme Corp',
        relationship_to_parent: 'root',
        target_persona: null,
      },
      {
        brand_context_id: 'sub_brand:acme-pro',
        name: 'Acme Pro',
        brand_scope: 'sub_brand',
        parent_brand: 'Acme Corp',
        relationship_to_parent: 'branded_house',
        target_persona: 'Enterprise IT',
      },
    ];

    render(<BrandContextSelector />);

    // Open dropdown
    fireEvent.click(screen.getByText('Acme Corp'));

    // Select Acme Pro
    fireEvent.click(screen.getByText('Acme Pro'));

    expect(mockSwitchBrand).toHaveBeenCalledWith('sub_brand:acme-pro');
  });

  it('is disabled when loading', () => {
    mockBrandContext.hasSubBrands = true;
    mockBrandContext.isLoading = true;
    mockBrandContext.activeBrand = {
      brand_context_id: 'parent',
      name: 'Acme Corp',
      brand_scope: 'parent',
    };

    render(<BrandContextSelector />);
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
  });
});
