"use client";

import { Share2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";
import { useConversationExists } from "@/state/useConversationExists";

import { ShareDialog } from "./ShareDialog";

export function ShareButton({
  conversationId,
  onPhone,
}: {
  conversationId: string;
  onPhone: boolean;
}) {
  const exists = useConversationExists(conversationId);
  const [open, setOpen] = useState(false);
  if (!exists) return null;
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size={onPhone ? "icon" : "sm"}
        aria-label="Share"
        onClick={() => setOpen(true)}
        className={cn(
          "transition-transform active:scale-[0.98]",
          onPhone
            ? "size-11 shrink-0"
            : "h-8 gap-1.5 rounded-full border border-border bg-background/85 px-3 text-xs shadow-sm backdrop-blur",
        )}
      >
        <Share2 className="size-3.5" aria-hidden />
        {onPhone ? null : <span>Share</span>}
      </Button>
      {open ? (
        <ShareDialog conversationId={conversationId} open onOpenChange={setOpen} />
      ) : null}
    </>
  );
}
