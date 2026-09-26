/**
 * The step layout each build arc leaves, as its UAT flow's Expect column names
 * it. The searches are the site's own; the organism, the ids and the counts are
 * read from the site at run time, never from here.
 */

import { COMBINE_SEARCH_NAME, type AstNode } from "./ast";

export const SIGNAL_PEPTIDE = "GenesWithSignalPeptide";
export const TRANSMEMBRANE = "GenesByTransmembraneDomains";
export const ORTHOLOGS = "GenesByOrthologs";
export const GENE_TYPE = "GenesByGeneType";
export const GO_TERM = "GenesByGoTerm";

/** A tree's shape: its step count, its searches and its combine operators, sorted. */
export interface Layout {
  steps: number;
  searches: string[];
  operators: string[];
}

export const LAYOUTS = {
  single: { steps: 1, searches: [SIGNAL_PEPTIDE], operators: [] },
  intersect: {
    steps: 3,
    searches: [TRANSMEMBRANE, SIGNAL_PEPTIDE].sort(),
    operators: ["INTERSECT"],
  },
  union: {
    steps: 3,
    searches: [TRANSMEMBRANE, SIGNAL_PEPTIDE].sort(),
    operators: ["UNION"],
  },
  minus: {
    steps: 3,
    searches: [TRANSMEMBRANE, SIGNAL_PEPTIDE].sort(),
    operators: ["MINUS"],
  },
  orthologs: {
    steps: 4,
    searches: [ORTHOLOGS, TRANSMEMBRANE, SIGNAL_PEPTIDE].sort(),
    operators: ["INTERSECT"],
  },
  "round-trip": {
    steps: 9,
    searches: [
      ORTHOLOGS,
      ORTHOLOGS,
      TRANSMEMBRANE,
      TRANSMEMBRANE,
      SIGNAL_PEPTIDE,
      SIGNAL_PEPTIDE,
    ].sort(),
    operators: ["INTERSECT", "INTERSECT", "INTERSECT"],
  },
  "count-question": { steps: 1, searches: [GENE_TYPE], operators: [] },
  go: { steps: 1, searches: [GO_TERM], operators: [] },
  "zero-then-relax": { steps: 1, searches: [TRANSMEMBRANE], operators: [] },
} satisfies Record<string, Layout>;

/** The shape of a stored tree, in the form `LAYOUTS` states it. */
export function layoutOf(nodes: readonly AstNode[]): Layout {
  return {
    steps: nodes.length,
    searches: nodes
      .filter((node) => node.searchName !== COMBINE_SEARCH_NAME)
      .map((node) => node.searchName ?? "")
      .sort(),
    operators: nodes
      .filter((node) => node.searchName === COMBINE_SEARCH_NAME)
      .map((node) => node.operator ?? "")
      .sort(),
  };
}
