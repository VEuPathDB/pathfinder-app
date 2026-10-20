"use client";

import { useAuiState } from "@assistant-ui/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";

import { MessageAction } from "@/components/ai-elements/message";
import { chatUrl, conversationIdFromPath } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";
import { forkStrategy } from "@pathfinder/shared/generated/hooks/useForkStrategy";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";

export function BranchMessageAction() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const siteId = useSessionStore((s) => s.selectedSite);
  const conversationId = conversationIdFromPath(pathname);
  const messageId = useAuiState((s) => s.message.id);

  const mutation = useMutation({
    mutationFn: async () => {
      if (conversationId == null) {
        throw new Error("Missing conversation context");
      }
      return forkStrategy(conversationId, { fromMessageId: messageId });
    },
    onSuccess: (fork) => {
      void queryClient.invalidateQueries({
        queryKey: listStrategiesQueryOptions({ siteId }).queryKey,
      });
      router.push(chatUrl(fork.id));
    },
    onError: (err) => {
      toast.error(
        err instanceof Error ? err.message : "Failed to branch this conversation",
      );
    },
  });

  return (
    <MessageAction
      tooltip="Branch to a new conversation from here"
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
    >
      <GitBranch />
    </MessageAction>
  );
}
