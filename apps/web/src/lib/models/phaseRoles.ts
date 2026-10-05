// Role names are data: a tier preset names the roles of the assistant it
// belongs to, and the tables below are how those names read to a user. A role
// with no label falls back to the name itself.

export const PHASE_LABELS: Record<string, string> = {
  lead: "Assistant",
  frame: "Planning",
  build: "Building",
  execution: "Building",
  verification: "Checking",
  recover_failed_steps: "Repairing",
  site_help: "Site help",
};

export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? phase;
}

// The roles a researcher picks a model for, each with the line its Settings
// row shows. A preset role outside this table runs on the deployment's tier.
export const PICKABLE_ROLE_DESCRIPTIONS = {
  lead: "Talks with you and decides what happens next.",
  frame: "Turns your question into a plan of searches and fills in their settings.",
  verification: "Checks the built strategy and reports what it found.",
  site_help: "Answers questions about the VEuPathDB sites and what they hold.",
} as const;

export type PickableRole = keyof typeof PICKABLE_ROLE_DESCRIPTIONS;

export function isPickableRole(role: string): role is PickableRole {
  return Object.hasOwn(PICKABLE_ROLE_DESCRIPTIONS, role);
}

/** The picks of the roles a researcher picks; the picks of other roles drop. */
export function pickableOnly<V>(
  picks: Readonly<Record<string, V>>,
): Partial<Record<PickableRole, V>> {
  return Object.fromEntries(
    Object.entries(picks).filter(([role]) => isPickableRole(role)),
  );
}

export function phaseDescription(role: PickableRole): string {
  return PICKABLE_ROLE_DESCRIPTIONS[role];
}
