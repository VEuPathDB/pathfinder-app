/**
 * The mock model's arc tokens. A message carries one `[[arc:<name>]]` and the
 * mock plays that arc on the site the conversation opened; a name outside this
 * union fails to compile.
 */

export const ARC_NAMES = [
  "single",
  "intersect",
  "union",
  "minus",
  "orthologs",
  "syntenic-orthologs",
  "round-trip",
  "go",
  "combined",
  "edit-param",
  "add-step",
  "delete-step",
  "delete-step-card",
  "replace-subtree",
  "clear",
  "count-question",
  "gene-question",
  "consult",
  "no-search-states-it",
  "cross-organism",
  "zero-then-relax",
  "proposal",
  "portal-only",
  "other-site-experiment",
  "off-topic",
  "remember",
  "recall-preference",
  "context",
  "second-build",
  "controls-test",
  "sweep",
  "separation",
  "variants",
  "eda-compare",
  "eda-compare-no-step",
  "eda-other-site",
  "save-gene-set",
  "export",
  "rename",
  "recap",
  "attachment",
  "frame-loop",
  "kinase-question",
  "impact",
  "assent",
  "echo",
] as const;

export type ArcName = (typeof ARC_NAMES)[number];

/** The token alone, as the mock reads it. */
export function arc(name: ArcName): string {
  return `[[arc:${name}]]`;
}

/** A researcher's sentence with the token after it. */
export function prompt(name: ArcName, text: string): string {
  return `${text} ${arc(name)}`;
}

/** The message the scripted injection judge refuses. */
export const INJECTION_TEST_MESSAGE = "[[pathfinder-injection-test]]";
