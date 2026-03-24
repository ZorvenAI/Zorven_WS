import { apiClient } from '@/lib/api';
import type { BrandContextEntry } from '@/types/brand-context';

export async function getBrandContextOptions(): Promise<BrandContextEntry[]> {
  try {
    const response = await apiClient.request(
      '/analytics/brand-context-options/'
    );
    if (!response.ok) return [];
    return response.json();
  } catch {
    return []; // Graceful fallback: empty = parent only
  }
}
