import type { MemoryItem, MemoryKind, MemoryListResponse } from "@pathfinder/shared";

/** How the app names each kind of memory: one of them, and a list of them. */
export const MEMORY_KIND_LABELS: Record<MemoryKind, { one: string; many: string }> = {
  gene_set_note: { one: "Gene set", many: "Gene sets" },
  strategy: { one: "Strategy", many: "Strategies" },
  preference: { one: "Preference", many: "Preferences" },
  knowledge: { one: "Knowledge", many: "Knowledge" },
  case: { one: "Case", many: "Cases" },
};

export interface MemorySectionItems {
  kind: MemoryKind;
  items: MemoryItem[];
}

/** A listing's memories grouped by kind, in the order every list shows them. */
export function memorySections(
  list: MemoryListResponse | undefined,
): MemorySectionItems[] {
  return [
    { kind: "gene_set_note", items: list?.geneSetNotes ?? [] },
    { kind: "strategy", items: list?.strategies ?? [] },
    { kind: "preference", items: list?.preferences ?? [] },
    { kind: "knowledge", items: list?.knowledge ?? [] },
    { kind: "case", items: list?.cases ?? [] },
  ];
}
