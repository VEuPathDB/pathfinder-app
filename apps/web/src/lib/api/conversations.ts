import { z } from "zod";

import type { InsertSavedRequest } from "@pathfinder/shared/generated/types/InsertSavedRequest";

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
  operator?: InsertSavedRequest["operator"];
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
  const base: InsertSavedRequest = {
    targetStepId: args.targetStepId,
    savedWdkStrategyId: args.savedWdkStrategyId,
  };
  const data: InsertSavedRequest =
    args.operator === undefined ? base : { ...base, operator: args.operator };
  const resp = await client<InsertSavedStrategyResult>({
    method: "post",
    url: `/api/v1/conversations/${args.conversationId}/insert-saved`,
    params: { siteId: args.siteId },
    data,
  });
  return resp.data;
}
