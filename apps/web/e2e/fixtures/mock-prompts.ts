/**
 * Deterministic prompts for the mock model that still classify as real
 * strategy-building requests in the current pipeline.
 */

export const MOCK_PLAN_PROMPT = "create step";
/** The reply that closes the plan arc, after FRAME, BUILD and VERIFY ran. */
export const MOCK_PLAN_REPLY = /Verified end-to-end/;
export const MOCK_DELEGATION_PROMPT = "create delegation";
export const MOCK_DELEGATION_DRAFT_PROMPT = "create delegation draft";
/** A build whose check tests the controls the mock names, so it leaves an evidence card. */
export const MOCK_CONTROLS_PROMPT = "create step and check it against my controls";
