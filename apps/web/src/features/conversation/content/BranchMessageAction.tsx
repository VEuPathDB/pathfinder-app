"use client";

import { useAuiState } from "@assistant-ui/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";

import { MessageAction } from "@/components/ai-elements/message";
import { toUserMessage } from "@/lib/api/errors";
import { chatUrl, conversationIdFromPath } from "@/lib/routes";
import { useSessionStore } from "@/state/useSessionStore";
import { forkStrategy } from "@strategist/shared/generated/hooks/useForkStrategy";
import { listStrategiesQueryOptions } from "@strategist/shared/generated/hooks/useListStrategies";

export function BranchMessageAction() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const siteId = useSessionStore((s) => s.selectedSite);
  const conversationId = conversationIdFromPath(pathname);
  const messageId = useAuiState((s) => s.message.id);
  const toastId = `branch-${messageId}`;

  const mutation = useMutation({
    onMutate: () => {
      toast.loading("Branching this conversation...", { id: toastId });
    },
    mutationFn: async () => {
      if (conversationId == null) {
        throw new Error("Missing conversation context");
      }
      return forkStrategy(conversationId, { fromMessageId: messageId });
    },
    onSuccess: (fork) => {
      toast.dismiss(toastId);
      void queryClient.invalidateQueries({
        queryKey: listStrategiesQueryOptions({ siteId }).queryKey,
      });
      router.push(chatUrl(fork.id));
    },
    onError: (err) => {
      toast.error(toUserMessage(err, "Could not branch this conversation"), {
        id: toastId,
      });
    },
  });

  return (
    <MessageAction
      tooltip="Branch to a new conversation from here"
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
      aria-busy={mutation.isPending}
    >
      {mutation.isPending ? <Loader2 className="animate-spin" /> : <GitBranch />}
    </MessageAction>
  );
}
