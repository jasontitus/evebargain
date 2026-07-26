/**
 * Format ISK values with thousands separators.
 * e.g., 1234567.89 -> "1,234,567.89 ISK"
 */
export function formatISK(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }) + ' ISK';
}

/**
 * Format a percentage value.
 * e.g., 0.1523 -> "15.2%"
 */
export function formatPercent(value: number): string {
  return (value * 100).toFixed(1) + '%';
}

/**
 * Format a relative time string.
 * e.g., "2 minutes ago"
 */
export function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/**
 * Compact ISK with no unit suffix, for dense tables where the column header
 * already says the unit and repeating " ISK" on every cell just costs width.
 * e.g., 1500000 -> "1.50M"
 */
export function formatISKShort(value: number): string {
  if (value >= 1_000_000_000) return (value / 1_000_000_000).toFixed(2) + 'B';
  if (value >= 1_000_000) return (value / 1_000_000).toFixed(2) + 'M';
  if (value >= 1_000) return (value / 1_000).toFixed(1) + 'K';
  return value.toFixed(0);
}

/**
 * Compact ISK format for large numbers.
 * e.g., 1500000 -> "1.5M ISK"
 */
export function formatISKCompact(value: number): string {
  if (value >= 1_000_000_000) {
    return (value / 1_000_000_000).toFixed(2) + 'B ISK';
  }
  if (value >= 1_000_000) {
    return (value / 1_000_000).toFixed(2) + 'M ISK';
  }
  if (value >= 1_000) {
    return (value / 1_000).toFixed(1) + 'K ISK';
  }
  return value.toFixed(2) + ' ISK';
}

/**
 * Cubic metres, at a precision that suits the magnitude: ore is 0.01 m3 and a
 * battleship is 500,000, so a fixed decimal count is wrong at one end or the
 * other.
 */
export function formatVolume(m3: number): string {
  if (m3 >= 1_000_000) return (m3 / 1_000_000).toFixed(2) + 'M';
  if (m3 >= 10_000) return (m3 / 1_000).toFixed(1) + 'K';
  if (m3 >= 10) return m3.toFixed(0);
  if (m3 >= 1) return m3.toFixed(1);
  return m3.toFixed(2);
}
