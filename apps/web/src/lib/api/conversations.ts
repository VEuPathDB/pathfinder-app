import { z } from "zod";

import { beginStrategy } from "@pathfinder/shared/generated/hooks/useBeginStrategy";

import { client } from "./client";
import { requestJson } from "./http";

const conversationDuplicateSchema = z.object({
  id: z.string(),
  name: z.string(),
});

type ConversationDuplicate = z.infer<typeof conversationDuplicateSchema>;

/** Duplicate a whole conversation (incl. its strategy) into a new copy. */
export async function duplicateConversation(
  conversationId: string,
): Promise<ConversationDuplicate> {
  return requestJson(
    conversationDuplicateSchema,
    `/api/v1/conversations/${conversationId}/duplicate`,
    { method: "POST" },
  );
}

interface InsertSavedStrategyArgs {
  conversationId: string;
  siteId: string;
  /** Empty when the thread has no steps: the saved strategy becomes the root. */
  targetStepId: string;
  savedWdkStrategyId: number;
  /** Absent when there is no step to combine with. */
  operator?: string | undefined;
}

interface InsertSavedStrategyResult {
  wdkStrategyId: number;
  insertedSavedWdkStrategyId: number;
  insertedSavedName: string;
  combineStepId: string;
}

/** Insert a saved strategy beside a step, or as the thread's own root. */
export async function insertSavedStrategy(
  args: InsertSavedStrategyArgs,
): Promise<InsertSavedStrategyResult> {
  const base = {
    targetStepId: args.targetStepId,
    savedWdkStrategyId: args.savedWdkStrategyId,
  };
  const resp = await client<InsertSavedStrategyResult>({
    method: "post",
    url: `/api/v1/conversations/${args.conversationId}/insert-saved`,
    params: { siteId: args.siteId },
    data: args.operator === undefined ? base : { ...base, operator: args.operator },
  });
  return resp.data;
}

/** Open a chat whose strategy starts from a saved one, and return its id. */
export async function startChatFromSavedStrategy(args: {
  siteId: string;
  name: string;
  savedWdkStrategyId: number;
}): Promise<string> {
  const conversationId = crypto.randomUUID();
  await beginStrategy(conversationId, { siteId: args.siteId, seedText: args.name });
  await insertSavedStrategy({
    conversationId,
    siteId: args.siteId,
    targetStepId: "",
    savedWdkStrategyId: args.savedWdkStrategyId,
  });
  return conversationId;
}
