/** Format a number with K/M abbreviation, trimming unnecessary decimals. */
export function formatCompactClean(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}K`;
  return String(n);
}

/** Format a price per million tokens. Zero reads as "Free". */
export function formatPrice(n: number): string {
  if (n === 0) return "Free";
  if (n < 0.01) return "<$0.01";
  return `$${n.toFixed(2)}`;
}
