"use client";

import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";

import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import {
  useDeleteWorkflow,
  type DeleteWorkflow,
} from "@/features/sidebar/hooks/useDeleteWorkflow";
import {
  useRenameWorkflow,
  type RenameWorkflow,
} from "@/features/sidebar/hooks/useRenameWorkflow";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { updateStrategy } from "@pathfinder/shared/generated/hooks/useUpdateStrategy";
import { duplicateConversation } from "@/lib/api/conversations";
import { toUserMessage } from "@/lib/api/errors";
import { chatRoot, chatUrl, conversationIdFromPath } from "@/lib/routes";

interface UseConversationSidebarActionsArgs {
  siteId: string;
  reportError: (message: string) => void;
}

interface ConversationSidebarActions extends RenameWorkflow, DeleteWorkflow {
  activeId: string | null;
  handleNewConversation: (assistantId?: string) => Promise<void>;
  handleToggleSaved: (item: ConversationItem) => Promise<void>;
  handleDuplicate: (item: ConversationItem) => Promise<void>;
}

export function useConversationSidebarActions({
  siteId,
  reportError,
}: UseConversationSidebarActionsArgs): ConversationSidebarActions {
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const activeId = conversationIdFromPath(pathname);

  const rename = useRenameWorkflow({ siteId, reportError });
  const deleteWorkflow = useDeleteWorkflow({
    siteId,
    reportError,
    activeChatId: activeId,
  });

  const listKey = listStrategiesQueryOptions({ siteId }).queryKey;

  const handleNewConversation = async (assistantId?: string): Promise<void> => {
    router.push(chatRoot(siteId, assistantId));
  };

  const handleToggleSaved = async (item: ConversationItem): Promise<void> => {
    const nextSaved = !item.isSaved;
    try {
      const updated = await updateStrategy(item.id, { isSaved: nextSaved });
      queryClient.setQueryData<ConversationResponse[]>(listKey, (old) =>
        (old ?? []).map((c) => (c.id === item.id ? updated : c)),
      );
    } catch (err) {
      reportError(
        toUserMessage(
          err,
          nextSaved
            ? "Failed to mark conversation as saved."
            : "Failed to unmark saved.",
        ),
      );
    }
  };

  const handleDuplicate = async (item: ConversationItem): Promise<void> => {
    try {
      const copy = await duplicateConversation(item.id);
      await queryClient.invalidateQueries({ queryKey: listKey });
      router.push(chatUrl(siteId, copy.id));
    } catch (err) {
      reportError(toUserMessage(err, "Failed to duplicate conversation."));
    }
  };

  return {
    activeId,
    handleNewConversation,
    handleToggleSaved,
    handleDuplicate,
    ...rename,
    ...deleteWorkflow,
  };
}
