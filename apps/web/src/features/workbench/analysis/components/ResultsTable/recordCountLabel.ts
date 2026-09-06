/** Label for a page of records, when the total may be unknown. */
export function recordCountLabel(
  count: number | null,
  recordType: string | null,
): string {
  const noun =
    recordType == null || recordType === "" ? "record" : recordType.replace(/_/g, " ");
  if (count == null) {
    return `${noun}s, count unavailable`;
  }
  return `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;
}
