// Role names are data: a tier preset names the roles of the assistant it
// belongs to, and the tables below are how those names read to a user. A role
// with no entry falls back to the name itself.

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

export const PHASE_DESCRIPTIONS: Record<string, string> = {
  lead: "Talks with you and decides what happens next.",
  frame: "Turns your question into a plan of searches and fills in their settings.",
  execution: "Builds the strategy and repairs any step the site refuses.",
  verification: "Checks the built strategy and reports what it found.",
  site_help: "Answers questions about the VEuPathDB sites and what they hold.",
};

export function phaseDescription(phase: string): string {
  return PHASE_DESCRIPTIONS[phase] ?? "";
}
