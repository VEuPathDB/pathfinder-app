/** Parse a string of gene IDs separated by newlines, commas, or tabs.
 *  Deduplicates and preserves first-occurrence order. */
export function parseGeneIds(text: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const raw of text.split(/[\n,\t]+/)) {
    const id = raw.trim();
    if (id && !seen.has(id)) {
      seen.add(id);
      result.push(id);
    }
  }
  return result;
}
