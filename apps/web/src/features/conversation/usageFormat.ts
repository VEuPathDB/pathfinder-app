const tokensCompact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const costFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const costSubCentFmt = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

export function formatTokens(tokens: number): string {
  return tokensCompact.format(tokens);
}

export function formatCost(cost: number): string {
  if (cost <= 0) return costFmt.format(0);
  if (cost < 0.01) return costSubCentFmt.format(cost);
  return costFmt.format(cost);
}

/** "12.3K, $0.004" - compact tokens and cost for a usage chip. */
export function formatUsage(tokens: number, costUsd: number | string): string {
  return `${formatTokens(tokens)}, ${formatCost(Number(costUsd))}`;
}
