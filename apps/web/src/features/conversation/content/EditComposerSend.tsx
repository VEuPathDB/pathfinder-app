"use client";

import { useAuiState, useEditComposer } from "@assistant-ui/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { forkStrategy } from "@pathfinder/shared/generated/hooks/useForkStrategy";
import { revertToMessage } from "@pathfinder/shared/generated/hooks/useRevertToMessage";
import { submitProductAction } from "@pathfinder/shared/generated/hooks/useSubmitProductAction";
import { conversationSnapshotOptions } from "@/features/conversation/api/conversationSnapshot";
import { strategyQueryKey } from "@/lib/api/strategy";
import { toUserMessage } from "@/lib/api/errors";
import { chatUrl } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";

import { BranchOrRevertDialog } from "./BranchOrRevertDialog";

const ROUTE_RE = /^\/([^/]+)\/conversation\/([^/?#]+)/;

function dialogError(branchError: unknown, revertError: unknown): string | null {
  if (branchError != null) return toUserMessage(branchError, "Could not branch");
  if (revertError != null) return toUserMessage(revertError, "Could not revert");
  return null;
}

export function EditComposerBranchOrRevert() {
  const messageId = useAuiState((s) => s.message.id);
  const parentId = useAuiState((s) => s.message.parentId);
  const composerText = useEditComposer((s) => s.text);
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const setPendingSubmission = useSessionStore((s) => s.setPendingUserSubmission);
  const bumpChatResetCounter = useSessionStore((s) => s.bumpChatResetCounter);

  const [dialogOpen, setDialogOpen] = useState(false);

  const match = pathname.match(ROUTE_RE);
  const siteId = match?.[1] ?? null;
  const conversationId = match?.[2] ?? null;

  const branchMutation = useMutation({
    mutationFn: async () => {
      if (conversationId === null || siteId === null || parentId === null) {
        throw new Error("Cannot branch from here");
      }
      return forkStrategy(conversationId, { fromMessageId: parentId });
    },
    onSuccess: (fork) => {
      if (siteId === null) return;
      setPendingSubmission({
        conversationId: fork.id,
        content: composerText.trim(),
      });
      setDialogOpen(false);
      router.push(chatUrl(siteId, fork.id));
    },
  });

  const revertMutation = useMutation({
    mutationFn: async () => {
      if (conversationId === null) throw new Error("No conversation");
      await revertToMessage(conversationId, { messageId });
      void submitProductAction({
        action: "undo_turn",
        streamId: messageId,
      }).catch((err: unknown) => {
        console.warn("submitProductAction(undo_turn) failed", err);
      });
    },
    onSuccess: async () => {
      if (conversationId === null) return;
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: conversationSnapshotOptions(conversationId).queryKey,
        }),
        queryClient.invalidateQueries({
          queryKey: strategyQueryKey(conversationId),
        }),
        queryClient.invalidateQueries({
          queryKey: ["conversations", conversationId, "scratchpad"],
        }),
      ]);
      setPendingSubmission({
        conversationId,
        content: composerText.trim(),
      });
      bumpChatResetCounter();
      setDialogOpen(false);
    },
  });

  const pending = branchMutation.isPending || revertMutation.isPending;

  const handleClick = () => {
    if (composerText.trim() === "") return;
    branchMutation.reset();
    revertMutation.reset();
    setDialogOpen(true);
  };

  return (
    <>
      <Button
        type="button"
        size="sm"
        onClick={handleClick}
        disabled={pending || composerText.trim() === ""}
        data-testid="edit-composer-branch-or-revert"
      >
        Save...
      </Button>
      <BranchOrRevertDialog
        open={dialogOpen}
        canBranch={parentId !== null}
        pending={pending}
        error={dialogError(branchMutation.error, revertMutation.error)}
        onBranch={() => branchMutation.mutate()}
        onRevert={() => revertMutation.mutate()}
        onCancel={() => setDialogOpen(false)}
      />
    </>
  );
}
