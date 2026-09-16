/** What the workbench knows about the reader's gene-set library right now. */
export type GeneSetLibraryState = "signed-out" | "loading" | "empty" | "populated";

interface GeneSetLibraryInput {
  signedIn: boolean;
  isFetched: boolean;
  count: number;
}

/**
 * The library state the workbench draws. A signed-out reader is never told the
 * library is empty: PathFinder has not asked for it.
 */
export function geneSetLibraryState({
  signedIn,
  isFetched,
  count,
}: GeneSetLibraryInput): GeneSetLibraryState {
  if (!signedIn) return "signed-out";
  if (!isFetched) return "loading";
  return count === 0 ? "empty" : "populated";
}
