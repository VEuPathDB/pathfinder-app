import { describe, expect, it } from "vitest";
import type { GroundedConstraint } from "@pathfinder/shared/generated/types/GroundedConstraint";

import { constraintSentences } from "./constraintSentences";

function entry(
  label: string,
  status: GroundedConstraint["status"],
  extra: Partial<GroundedConstraint> = {},
): GroundedConstraint {
  return {
    constraint: {
      kind: "property",
      requestedValue: label,
      label,
      source: "user_explicit",
      hard: true,
    },
    status,
    ...extra,
  };
}

describe("constraintSentences", () => {
  it("names the requirements no step covers, which the unmet count leaves out", () => {
    expect(
      constraintSentences([
        entry("enzymes", "not_verified", { unverified: "no_step_states_it" }),
        entry("interfere with host proteins", "not_verified", {
          unverified: "no_step_states_it",
        }),
      ]),
    ).toEqual([
      "2 requirements are not in any step: enzymes, interfere with host proteins.",
    ]);
  });

  it("shows only the sentences that apply, problems first", () => {
    expect(
      constraintSentences([
        entry("secreted", "grounded"),
        entry("RNA-Seq", "substituted"),
        entry("P. falciparum", "ungroundable"),
        entry("enzymes", "not_verified", { unverified: "no_step_states_it" }),
        entry("fold change", "not_verified", { unverified: "no_value_to_compare" }),
        entry("expressed", "not_verified", { unverified: "untyped" }),
        entry("top 10 percent", "provisional"),
      ]),
    ).toEqual([
      "2 requirements are not met: RNA-Seq, P. falciparum.",
      "1 requirement is not in any step: enzymes.",
      "2 requirements could not be checked against a step: fold change, expressed.",
      "1 requirement waits for the strategy to be built: top 10 percent.",
      "1 requirement is met: secreted.",
    ]);
  });

  it("leaves out a requirement the researcher withdrew or replaced", () => {
    expect(
      constraintSentences([
        entry("secreted", "grounded"),
        entry("enzymes", "not_verified", {
          unverified: "no_step_states_it",
          lifecycle: { state: "withdrawn", turnId: "turn-2" },
        }),
        entry("RNA-Seq", "substituted", {
          lifecycle: { state: "replaced", by: "abc123" },
        }),
      ]),
    ).toEqual(["1 requirement is met: secreted."]);
  });

  it("says nothing when there are no requirements", () => {
    expect(constraintSentences([])).toEqual([]);
  });
});
