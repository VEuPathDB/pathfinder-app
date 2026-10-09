import { describe, expect, test } from "vitest";
import {
  buildPhyleticTree,
  buildSpeciesLists,
  decodeProfilePattern,
  encodeProfilePattern,
  leafStates,
  resolveTerms,
  type TriState,
} from "./phyleticProfileLogic";

import { qaRecording } from "@/lib/testing/qaRecording";

interface UnresolvedExpectation {
  included_unknown?: string[];
  excluded_unknown?: string[];
  conflicts?: string[];
}

interface ConformanceCase {
  name: string;
  included: string[];
  excluded: string[];
  profile_pattern?: string;
  included_species?: string;
  excluded_species?: string;
  leaf_states?: Record<string, string>;
  unresolved?: UnresolvedExpectation;
  tsSkip?: boolean;
  tsSkipReason?: string;
}

interface DecodeCase {
  name: string;
  pattern: string;
  widget: Record<string, string>;
}

interface Fixture {
  term_map: string[][];
  indent_map: string[][];
  cases: ConformanceCase[];
  decode: DecodeCase[];
}

const recorded = qaRecording(
  new URL(
    "../../../../../../../packages/spec/phyletic_conformance.json",
    import.meta.url,
  ),
);
const data = (recorded ?? {
  term_map: [],
  indent_map: [],
  cases: [],
  decode: [],
}) as Fixture;
const roots = buildPhyleticTree(data.term_map, data.indent_map);

/** The widget holds one tri-state per code, keyed by the node the user clicked. */
function selection(included: string[], excluded: string[]): Map<string, TriState> {
  const states = new Map<string, TriState>();
  for (const code of included) states.set(code, "include");
  for (const code of excluded) states.set(code, "exclude");
  return states;
}

function asRecord(states: Map<string, TriState>): Record<string, string> {
  return Object.fromEntries(states);
}

describe.skipIf(recorded === null)(
  "phyletic conformance (shared FE/BE fixture)",
  () => {
    for (const c of data.cases) {
      if (c.tsSkip === true) {
        test.skip(`${c.name} - ${c.tsSkipReason}`, () => {});
        continue;
      }
      test(c.name, () => {
        const includedTerms = resolveTerms(roots, c.included);
        const excludedTerms = resolveTerms(roots, c.excluded);

        if (c.unresolved !== undefined) {
          expect(includedTerms.unknown).toEqual(c.unresolved.included_unknown ?? []);
          expect(excludedTerms.unknown).toEqual(c.unresolved.excluded_unknown ?? []);
          const known = c.included.length + c.excluded.length;
          const unknown = includedTerms.unknown.length + excludedTerms.unknown.length;
          expect(includedTerms.codes.length + excludedTerms.codes.length).toBe(
            known - unknown,
          );
          return;
        }

        expect(includedTerms.unknown).toEqual([]);
        expect(excludedTerms.unknown).toEqual([]);

        const states = selection(includedTerms.codes, excludedTerms.codes);
        const leaves = leafStates(states, roots);

        if (c.leaf_states !== undefined) {
          expect(asRecord(leaves)).toEqual(c.leaf_states);
        }

        expect(encodeProfilePattern(leaves)).toBe(c.profile_pattern);

        const lists = buildSpeciesLists(states);
        expect(lists.included).toBe(c.included_species);
        expect(lists.excluded).toBe(c.excluded_species);
      });
    }
  },
);

describe.skipIf(recorded === null)(
  "phyletic conformance decode (shared FE/BE fixture)",
  () => {
    for (const d of data.decode) {
      test(d.name, () => {
        expect(asRecord(decodeProfilePattern(d.pattern))).toEqual(d.widget);
      });
    }
  },
);
