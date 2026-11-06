import type { GroundedConstraint } from "@pathfinder/shared/generated/types/GroundedConstraint";

type Group = "not_met" | "no_step" | "unchecked" | "waiting" | "met";

const GROUP_ORDER: readonly Group[] = [
  "not_met",
  "no_step",
  "unchecked",
  "waiting",
  "met",
];

const PREDICATE: Record<Group, { one: string; many: string }> = {
  not_met: { one: "is not met", many: "are not met" },
  no_step: { one: "is not in any step", many: "are not in any step" },
  unchecked: {
    one: "could not be checked against a step",
    many: "could not be checked against a step",
  },
  waiting: {
    one: "waits for the strategy to be built",
    many: "wait for the strategy to be built",
  },
  met: { one: "is met", many: "are met" },
};

function groupOf(entry: GroundedConstraint): Group {
  switch (entry.status) {
    case "grounded":
      return "met";
    case "provisional":
      return "waiting";
    case "substituted":
    case "ungroundable":
      return "not_met";
    case "not_verified":
      return entry.unverified === "no_step_states_it" ? "no_step" : "unchecked";
  }
}

function isRetired(entry: GroundedConstraint): boolean {
  const state = entry.lifecycle?.state;
  return state === "withdrawn" || state === "replaced";
}

export function constraintSentences(grounded: readonly GroundedConstraint[]): string[] {
  const labels = new Map<Group, string[]>();
  for (const entry of grounded) {
    if (isRetired(entry)) continue;
    const group = groupOf(entry);
    labels.set(group, [...(labels.get(group) ?? []), entry.constraint.label]);
  }
  return GROUP_ORDER.flatMap((group) => {
    const names = labels.get(group);
    if (names === undefined) return [];
    const one = names.length === 1;
    const noun = one ? "requirement" : "requirements";
    const predicate = one ? PREDICATE[group].one : PREDICATE[group].many;
    return [`${String(names.length)} ${noun} ${predicate}: ${names.join(", ")}.`];
  });
}
