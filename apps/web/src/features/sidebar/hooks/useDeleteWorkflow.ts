"use client";

/**
 * Delete, restore and permanent delete for the conversation sidebar. A delete
 * moves the conversation to Recently deleted unless `deleteLinkedStrategy` asks
 * the site to delete its strategy too, which is the only path that edits the site.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { listDismissedStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListDismissedStrategies";
import { deleteStrategy } from "@pathfinder/shared/generated/hooks/useDeleteStrategy";
import { dismissConversation } from "@pathfinder/shared/generated/hooks/useDismissConversation";
import { restoreStrategy } from "@pathfinder/shared/generated/hooks/useRestoreStrategy";
import { toUserMessage } from "@/lib/api/errors";
import { chatRoot } from "@/lib/routes";

interface UseDeleteWorkflowArgs {
  siteId: string;
  reportError: (message: string) => void;
  activeChatId: string | null;
}

export interface DeleteWorkflow {
  deleteTarget: ConversationItem | null;
  isDeleting: boolean;
  setDeleteTarget: (item: ConversationItem | null) => void;
  confirmDelete: (options?: { deleteLinkedStrategy?: boolean }) => Promise<void>;

  handleRestore: (conversationId: string) => Promise<void>;

  permanentDeleteTarget: string | null;
  setPermanentDeleteTarget: (id: string | null) => void;
  confirmPermanentDelete: () => Promise<void>;
}

export function useDeleteWorkflow({
  siteId,
  reportError,
  activeChatId,
}: UseDeleteWorkflowArgs): DeleteWorkflow {
  const queryClient = useQueryClient();
  const router = useRouter();

  const [deleteTarget, setDeleteTarget] = useState<ConversationItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [permanentDeleteTarget, setPermanentDeleteTarget] = useState<string | null>(
    null,
  );

  const listKey = listStrategiesQueryOptions({ siteId }).queryKey;
  const dismissedKey = listDismissedStrategiesQueryOptions({ siteId }).queryKey;

  const confirmDelete = async (options: { deleteLinkedStrategy?: boolean } = {}) => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    const target = deleteTarget;
    try {
      if (activeChatId === target.id) {
        router.push(chatRoot(siteId));
      }

      if (options.deleteLinkedStrategy === true) {
        // Explicit opt-in: hard-delete the chat AND its WDK strategy.
        queryClient.setQueryData<ConversationResponse[]>(listKey, (old) =>
          (old ?? []).filter((c) => c.id !== target.id),
        );
        try {
          await deleteStrategy(target.id, { deleteFromWdk: true });
        } catch (err) {
          queryClient.setQueryData<ConversationResponse[]>(listKey, (old) => [
            target.chat,
            ...(old ?? []).filter((c) => c.id !== target.id),
          ]);
          reportError(toUserMessage(err, "Failed to delete conversation."));
        } finally {
          void queryClient.invalidateQueries({ queryKey: listKey });
          void queryClient.invalidateQueries({ queryKey: dismissedKey });
        }
        return;
      }

      // Default: a soft delete to Recently deleted; the site strategy stays.
      queryClient.setQueryData<ConversationResponse[]>(listKey, (old) =>
        (old ?? []).filter((c) => c.id !== target.id),
      );
      queryClient.setQueryData<ConversationResponse[]>(dismissedKey, (old) => [
        target.chat,
        ...(old ?? []).filter((c) => c.id !== target.id),
      ]);
      try {
        await dismissConversation(target.id);
      } catch (err) {
        queryClient.setQueryData<ConversationResponse[]>(listKey, (old) => [
          target.chat,
          ...(old ?? []).filter((c) => c.id !== target.id),
        ]);
        queryClient.setQueryData<ConversationResponse[]>(dismissedKey, (old) =>
          (old ?? []).filter((c) => c.id !== target.id),
        );
        reportError(
          toUserMessage(err, "Failed to move the conversation to Recently deleted."),
        );
      } finally {
        void queryClient.invalidateQueries({ queryKey: listKey });
        void queryClient.invalidateQueries({ queryKey: dismissedKey });
      }
    } finally {
      setIsDeleting(false);
      setDeleteTarget(null);
    }
  };

  const handleRestore = async (conversationId: string) => {
    try {
      await restoreStrategy(conversationId);
    } catch (err) {
      reportError(toUserMessage(err, "Failed to restore conversation."));
    } finally {
      void queryClient.invalidateQueries({ queryKey: listKey });
      void queryClient.invalidateQueries({ queryKey: dismissedKey });
    }
  };

  const confirmPermanentDelete = async () => {
    if (permanentDeleteTarget === null) return;
    const id = permanentDeleteTarget;
    try {
      await deleteStrategy(id);
      queryClient.setQueryData<ConversationResponse[]>(dismissedKey, (old) =>
        (old ?? []).filter((c) => c.id !== id),
      );
    } catch (err) {
      reportError(toUserMessage(err, "Failed to permanently delete conversation."));
    } finally {
      void queryClient.invalidateQueries({ queryKey: listKey });
      void queryClient.invalidateQueries({ queryKey: dismissedKey });
      setPermanentDeleteTarget(null);
    }
  };

  return {
    deleteTarget,
    isDeleting,
    setDeleteTarget,
    confirmDelete,
    handleRestore,
    permanentDeleteTarget,
    setPermanentDeleteTarget,
    confirmPermanentDelete,
  };
}
