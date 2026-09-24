"use client";

import { useAuiState } from "@assistant-ui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { toast } from "sonner";

import { MessageAction } from "@/components/ai-elements/message";
import { toUserMessage } from "@/lib/api/errors";
import { clearMessageRating } from "@pathfinder/shared/generated/hooks/useClearMessageRating";
import { listMessageRatingsQueryOptions } from "@pathfinder/shared/generated/hooks/useListMessageRatings";
import { rateMessage } from "@pathfinder/shared/generated/hooks/useRateMessage";
import type { Rating } from "@pathfinder/shared/generated/types/Rating";

import { useConversationId } from "../useConversationId";

interface RateButtonsProps {
  conversationId: string;
  messageId: string;
}

/** The like and dislike controls of one assistant message. A draft thread
 * has no id yet, so it has nothing to rate. */
export function RateMessageActions() {
  const conversationId = useConversationId();
  const messageId = useAuiState((s) => s.message.id);
  if (conversationId === null) return null;
  return <RateButtons conversationId={conversationId} messageId={messageId} />;
}

function RateButtons({ conversationId, messageId }: RateButtonsProps) {
  const queryClient = useQueryClient();
  const ratings = listMessageRatingsQueryOptions(conversationId);
  const saved = useQuery({
    ...ratings,
    select: (list) =>
      list.ratings.find((r) => r.messageId === messageId)?.rating ?? null,
  });
  const rate = useMutation({
    // One scope per message, so its clicks reach the server in order.
    scope: { id: `rating:${messageId}` },
    mutationFn: async (next: Rating | null) => {
      if (next === null) {
        await clearMessageRating(conversationId, messageId);
        return;
      }
      await rateMessage(conversationId, messageId, { rating: next });
    },
    onError: (err) => {
      toast.error(toUserMessage(err, "The rating was not saved."));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ratings.queryKey }),
  });

  const shown = rate.isPending ? rate.variables : (saved.data ?? null);
  const toggle = (value: Rating) => rate.mutate(shown === value ? null : value);

  return (
    <>
      <MessageAction
        tooltip="Good response"
        aria-pressed={shown === "like"}
        onClick={() => toggle("like")}
      >
        <ThumbsUp />
      </MessageAction>
      <MessageAction
        tooltip="Bad response"
        aria-pressed={shown === "dislike"}
        onClick={() => toggle("dislike")}
      >
        <ThumbsDown />
      </MessageAction>
    </>
  );
}
