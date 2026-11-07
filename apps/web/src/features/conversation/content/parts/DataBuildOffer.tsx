"use client";

import { useAuiState } from "@assistant-ui/react";
import type { BuildOfferPayload } from "@pathfinder/shared";
import { Hammer } from "lucide-react";
import type { ReactElement } from "react";

import { Button } from "@/components/ui/button";
import { countNoun } from "@/lib/utils/countNoun";
import { useThreadModeStore } from "@/state/useThreadModeStore";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { useConversationId } from "../../useConversationId";

export function DataBuildOffer({
  data,
}: {
  data: BuildOfferPayload;
}): ReactElement | null {
  const isLast = useAuiState((s) => s.message.isLast);
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const conversationId = useConversationId();
  const setMode = useThreadModeStore((s) => s.setMode);
  const chat = useChatHelpers();
  if (!isLast || conversationId === null) return null;
  return (
    <div
      data-testid="build-offer"
      className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2 text-sm"
    >
      <span className="text-muted-foreground">
        {data.label} ({data.geneCount.toLocaleString()}{" "}
        {countNoun("transcript", data.geneCount)})
      </span>
      <Button
        size="sm"
        disabled={isRunning}
        onClick={() => {
          setMode(conversationId, "build");
          void chat.sendMessage({ text: `Build "${data.label}".` });
        }}
      >
        <Hammer className="mr-1 size-4" aria-hidden /> Build it
      </Button>
    </div>
  );
}
