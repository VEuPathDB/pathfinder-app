"use client";

import { useAuiState } from "@assistant-ui/react";
import { RefreshCw } from "lucide-react";

import { MessageAction } from "@/components/ai-elements/message";
import { recordProductEvent } from "@/lib/api/productEvents";

import { useConversationId } from "../useConversationId";

export function RegenerateAction(props: { onClick?: (e: React.MouseEvent) => void }) {
  const message = useAuiState((s) => s.message);
  const conversationId = useConversationId();
  const handleClick = (e: React.MouseEvent) => {
    recordProductEvent({
      event: "assistant_regenerated",
      messageId: message.id,
      conversationId,
    });
    props.onClick?.(e);
  };
  return (
    <MessageAction tooltip="Regenerate" onClick={handleClick}>
      <RefreshCw />
    </MessageAction>
  );
}
