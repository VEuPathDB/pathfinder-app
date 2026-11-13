import type { AccountReads, AlwaysAccountReads } from "@strategist/shared";
import { accountReadsSchema } from "@strategist/shared/generated/zod/accountReadsSchema";
import { alwaysAccountReadsSchema } from "@strategist/shared/generated/zod/alwaysAccountReadsSchema";

import { requestJson } from "@/lib/api/http";

export const ALWAYS_ACCOUNT_READS_KEY = ["me", "account-reads"] as const;

export async function allowInThisConversation(
  conversationId: string,
): Promise<AccountReads> {
  return await requestJson(
    accountReadsSchema,
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/account-reads`,
    { method: "PUT", body: { allowed: true } },
  );
}

export async function getAlwaysAllowed(): Promise<AlwaysAccountReads> {
  return await requestJson(alwaysAccountReadsSchema, "/api/v1/me/account-reads");
}

export async function setAlwaysAllowed(always: boolean): Promise<AlwaysAccountReads> {
  return await requestJson(alwaysAccountReadsSchema, "/api/v1/me/account-reads", {
    method: "PUT",
    body: { always },
  });
}
