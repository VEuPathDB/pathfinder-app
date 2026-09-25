"use client";

import { useAuiState } from "@assistant-ui/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";

import { MessageAction } from "@/components/ai-elements/message";
import { chatUrl } from "@/lib/routes";
import { forkStrategy } from "@pathfinder/shared/generated/hooks/useForkStrategy";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";

const ROUTE_RE = /^\/([^/]+)\/conversation\/([^/?#]+)/;

export function BranchMessageAction() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const match = pathname.match(ROUTE_RE);
  const siteId = match?.[1] ?? null;
  const conversationId = match?.[2] ?? null;
  const messageId = useAuiState((s) => s.message.id);

  const mutation = useMutation({
    mutationFn: async () => {
      if (conversationId == null || siteId == null) {
        throw new Error("Missing conversation or site context");
      }
      return forkStrategy(conversationId, { fromMessageId: messageId });
    },
    onSuccess: (fork) => {
      if (siteId == null) return;
      void queryClient.invalidateQueries({
        queryKey: listStrategiesQueryOptions({ siteId }).queryKey,
      });
      router.push(chatUrl(siteId, fork.id));
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
