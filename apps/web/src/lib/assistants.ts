// The assistants this deployment serves. Mirrors the backend composition root
// (pathfinder.assistants.registry); the ids are the ones the chat body and
// ConversationResponse carry.

export const DEFAULT_ASSISTANT_ID = "pathfinder";
export const SITE_HELP_ASSISTANT_ID = "site_help";

export interface AssistantChoice {
  id: string;
  label: string;
  /** What the assistant does, for the reader about to open a thread with it. */
  blurb: (siteName: string) => string;
}

export const ASSISTANT_CHOICES: readonly AssistantChoice[] = [
  {
    id: DEFAULT_ASSISTANT_ID,
    label: "Strategy builder",
    blurb: (siteName) =>
      `Build and refine multi-step ${siteName} search strategies with guided ` +
      `parameter selection and validation.`,
  },
  {
    id: SITE_HELP_ASSISTANT_ID,
    label: "Site help",
    blurb: () =>
      "Find your way around the VEuPathDB sites: which site covers an " +
      "organism, and what each one lets you search.",
  },
];

export function assistantChoice(assistantId: string): AssistantChoice | null {
  return ASSISTANT_CHOICES.find((choice) => choice.id === assistantId) ?? null;
}

export function assistantLabel(assistantId: string): string {
  return assistantChoice(assistantId)?.label ?? assistantId;
}

/**
 * The assistant a thread runs under. Mirrors the backend rule: a thread that
 * exists keeps the assistant it was created with, and only a thread that does
 * not exist yet takes the one the URL names.
 */
export function resolveAssistantId({
  existing,
  requested,
}: {
  existing?: string | null | undefined;
  requested?: string | null | undefined;
}): string {
  if (existing != null && existing !== "") return existing;
  if (requested != null && assistantChoice(requested) !== null) return requested;
  return DEFAULT_ASSISTANT_ID;
}
