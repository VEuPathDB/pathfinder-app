/** The phrase every count surface uses for a count that was never measured. */
const COUNT_NOT_AVAILABLE = "count not available";

/** One count clause: the genes a strategy holds, or the phrase that says
 * nobody measured them. Zero is a result and stays a number. */
export function geneCountClause(count: number | null): string {
  if (count === null) return COUNT_NOT_AVAILABLE;
  return `${count.toLocaleString()} genes`;
}
