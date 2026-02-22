/**
 * ISO 10668 formatting helpers for currency, NPV, and percentage values.
 */

/** Format a number as currency — e.g. 1137236.01 → "$1,137,236" */
export function formatCurrency(
  value: number,
  currency = 'USD',
  decimals = 0,
): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Format a number in compact notation — e.g. 1137236 → "$1.1M" */
export function formatCompact(value: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

/** Format a decimal as a percentage — e.g. 0.04 → "4.0%" */
export function formatPercent(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}
