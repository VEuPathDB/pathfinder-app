/** A numbered exhibit is a figure or a table; the two counters run apart. */
export type ExhibitKind = "figure" | "table";

export interface ExhibitIdentity {
  kind: ExhibitKind;
  /** Null while the thread cannot supply a number, which leaves the exhibit
   * unnumbered and unanchored. */
  number: number | null;
}

const LABELS: Record<ExhibitKind, string> = { figure: "Figure", table: "Table" };

/** The DOM id a citation of this exhibit jumps to. */
export function exhibitAnchorId(kind: ExhibitKind, number: number): string {
  return `${kind}-${String(number)}`;
}

/** How the exhibit is named in a caption and in a cross-reference. */
export function exhibitLabel(kind: ExhibitKind, number: number): string {
  return `${LABELS[kind]} ${String(number)}`;
}
