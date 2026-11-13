"use client";

/**
 * Rename workflow for the conversation sidebar.
 *
 * Owns inline-rename UI state (which item is being renamed, the current
 * rename value) and commits renames to the chats API.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { ConversationItem } from "@/features/sidebar/components/conversationSidebarTypes";
import { listStrategiesQueryOptions } from "@strategist/shared/generated/hooks/useListStrategies";
import { listDismissedStrategiesQueryOptions } from "@strategist/shared/generated/hooks/useListDismissedStrategies";
import { updateStrategy } from "@strategist/shared/generated/hooks/useUpdateStrategy";
import { toUserMessage } from "@/lib/api/errors";

interface UseRenameWorkflowArgs {
  siteId: string;
  reportError: (message: string) => void;
}

export interface RenameWorkflow {
  renamingId: string | null;
  renameValue: string;
  setRenameValue: (v: string) => void;
  startRename: (item: ConversationItem) => void;
  commitRename: (item: ConversationItem) => Promise<void>;
  cancelRename: () => void;
}

export function useRenameWorkflow({
  siteId,
  reportError,
}: UseRenameWorkflowArgs): RenameWorkflow {
  const queryClient = useQueryClient();
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const startRename = (item: ConversationItem) => {
    setRenamingId(item.id);
    setRenameValue(item.title);
  };

  const commitRename = async (item: ConversationItem) => {
    const next = renameValue.trim();
    if (next === "" || next === item.title) {
      setRenamingId(null);
      return;
    }
    try {
      await updateStrategy(item.id, { name: next });
      void queryClient.invalidateQueries({
        queryKey: listStrategiesQueryOptions({ siteId }).queryKey,
      });
      void queryClient.invalidateQueries({
        queryKey: listDismissedStrategiesQueryOptions({ siteId }).queryKey,
      });
    } catch (err) {
      reportError(toUserMessage(err, "Failed to rename conversation."));
    }
    setRenamingId(null);
  };

  const cancelRename = () => {
    setRenamingId(null);
  };

  return {
    renamingId,
    renameValue,
    setRenameValue,
    startRename,
    commitRename,
    cancelRename,
  };
}
