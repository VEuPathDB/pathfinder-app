import type { InvestigationLedger } from "@pathfinder/shared/generated/types/InvestigationLedger";
import { investigationLedgerSchema } from "@pathfinder/shared/generated/zod/investigationLedgerSchema";

/**
 * Read an `InvestigationLedger` off a stored `data-ledger-update` payload.
 * A payload the schema rejects yields null and the panel shows nothing.
 */
export function normalizeLedgerPayload(raw: unknown): InvestigationLedger | null {
  const parsed = investigationLedgerSchema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}
