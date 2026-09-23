/** WDK counts a transcript answer in genes, so its count names genes. */
const COUNTED_AS: Record<string, string> = { transcript: "gene" };

/** The noun a step count of this record type reads as. */
export function countNoun(
  recordType: string | null | undefined,
  count: number,
): string {
  const noun =
    recordType == null || recordType === ""
      ? "result"
      : (COUNTED_AS[recordType] ?? recordType.replace(/_/g, " "));
  return count === 1 ? noun : `${noun}s`;
}
