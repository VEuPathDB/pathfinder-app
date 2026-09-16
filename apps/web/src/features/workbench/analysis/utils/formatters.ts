/** Shared formatters for ResultsDashboard sections. */
export function pct(v: number | null | undefined): string {
  if (v == null) return "-";
  return `${(v * 100).toFixed(1)}%`;
}

export function fmtNum(v: number | null | undefined, d = 3): string {
  if (v == null) return "-";
  return v.toFixed(d);
}

/** Format a parameter value: integers plain, otherwise 2 decimals. */
export function fmtParamValue(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}
