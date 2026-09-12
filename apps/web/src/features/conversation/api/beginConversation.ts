import { beginStrategy } from "@pathfinder/shared/generated/hooks/useBeginStrategy";
import type {
  BeginStrategyMutationRequest,
  BeginStrategyMutationResponse,
} from "@pathfinder/shared/generated/types/BeginStrategy";
import { useSessionStore } from "@/state/useSessionStore";

/** Create the conversation row, and record that it now exists. */
export async function beginConversation(
  conversationId: string,
  body: BeginStrategyMutationRequest,
): Promise<BeginStrategyMutationResponse> {
  const begun = await beginStrategy(conversationId, body);
  useSessionStore.getState().markConversationCreated(conversationId);
  return begun;
}
