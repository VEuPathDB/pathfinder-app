/**
 * Prompts and reply patterns the thread-surgery journeys share.
 *
 * Each prompt names one arc of the deterministic mock script, so a spec can
 * anchor a branch on a reply that is unique in its thread.
 */

/**
 * The site these journeys build on. Its search listing fits in one FRAME
 * request, and the organisms below are its own.
 */
export const SITE_ID = "plasmodb";

/** Builds a one-leaf strategy and verifies cleanly. */
export const BUILD_ONE = "create step for tryptophan synthase";

/** Patches the built strategy's organism, leaving the step count alone. */
export const EDIT_ORGANISM =
  "Swap the organism on the taxon criterion and keep the rest.";

/** The organism a fresh build binds, and the one the edit substitutes. */
export const BUILT_ORGANISM = "Plasmodium falciparum 3D7";
export const EDITED_ORGANISM = "Plasmodium vivax P01";

/** Reads one Ledger section back, dispatching no sub-agent. */
export const RECALL = "Recap what I have asked so far.";

/** The clean-verification reply. Unique in a thread with one build. */
export const VERIFIED = /Verified end-to-end/;

/** The reply of the organism-edit arc. */
export const SUBSTITUTED = /Substituted the organism/;

/** The reply of the recall arc. */
export const RECALLED = /This conversation already carries:/;

/** The plain echo reply for `text`, which calls no tool. */
export function echoOf(text: string): RegExp {
  return new RegExp(`\\[mock\\] ${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`);
}
