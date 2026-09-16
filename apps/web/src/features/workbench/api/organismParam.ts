import type { ParamSpec } from "@pathfinder/shared";
import { extractVocabOptions } from "@/lib/utils/vocab";

// A site's taxon tree runs to a few thousand terms on the largest databases.
const VOCAB_SCAN_LIMIT = 20_000;

export interface OrganismParam {
  /** The WDK parameter name a batch overrides. */
  name: string;
  /** The organisms of that parameter which the site declares. */
  organisms: string[];
}

/**
 * The parameter of a search whose vocabulary carries the site's organisms.
 * The vocabulary decides, not the name. Null when no parameter offers one.
 */
export function organismParamOf(
  specs: readonly ParamSpec[],
  siteOrganisms: readonly string[],
): OrganismParam | null {
  const declared = new Set(siteOrganisms);
  for (const spec of specs) {
    const organisms = extractVocabOptions(spec.vocabulary, VOCAB_SCAN_LIMIT)
      .map((option) => option.value)
      .filter((value) => declared.has(value));
    if (organisms.length > 0) return { name: spec.name, organisms };
  }
  return null;
}
