/**
 * Attribute filtering for distribution exploration.
 *
 * WDK gene records have 100+ attributes. Most are visualization URLs, genome
 * browser links, graph images, or internal fields. We use VEuPathDB's own
 * naming conventions to identify non-distributable columns.
 */

import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";

/** Exact attribute names to exclude. */
const BLOCKED_NAMES = new Set([
  "primary_key",
  "project",
  "dataset_id",
  "start_min_text",
  "end_max_text",
  "gff_seqid",
  "gff_fstart",
  "gff_fend",
]);

/** Substrings anywhere in the name that indicate non-distributable columns. */
const BLOCKED_SUBSTRINGS = [
  "url",
  "jbrowse",
  "gbrowse",
  "pbrowse",
  "browse",
  "apollo",
  "gtracks",
  "overview",
  "highlight",
  "context_start",
  "context_end",
  "zoom_context",
  "_rsrc_",
  "expr_graph",
  "pct_graph",
];

/** Prefixes that indicate internal or non-distributable columns. */
const BLOCKED_PREFIXES = ["wdk_", "j_", "lc_", "link"];

/** Suffixes that indicate non-distributable columns. */
const BLOCKED_SUFFIXES = [
  "link",
  "_graph",
  "_img",
  "_filename",
  "_help",
  "_warn",
  "_warning",
  "_prefix",
  "_partial",
];

/** Pattern for RNA-seq sample columns (pan_NNNN). */
const SAMPLE_COLUMN_RE = /^pan_\d+$/;

export function isDistributableAttr(a: RecordAttribute): boolean {
  if (a.isDisplayable === false || a.type === "link") return false;

  const n = a.name.toLowerCase();

  if (BLOCKED_NAMES.has(n)) return false;
  if (BLOCKED_SUBSTRINGS.some((s) => n.includes(s))) return false;
  if (BLOCKED_PREFIXES.some((p) => n.startsWith(p))) return false;
  if (BLOCKED_SUFFIXES.some((s) => n.endsWith(s))) return false;
  if (SAMPLE_COLUMN_RE.test(n)) return false;

  return true;
}
