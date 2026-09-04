"use client";

import { ThreadPrimitive } from "@assistant-ui/react";
import { ArrowDownIcon } from "lucide-react";
import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";
import { THREAD_BLOCK_GAP } from "@/components/ai-elements/rhythm";
import { cn } from "@/lib/utils/cn";

export type ConversationProps = ComponentProps<typeof ThreadPrimitive.Viewport>;

/**
 * The thread's scroll surface. The viewport primitive owns auto-scroll, so a
 * message the researcher sends from a scrolled position brings the thread back
 * to the bottom.
 */
export const Conversation = ({ className, ...props }: ConversationProps) => (
  <ThreadPrimitive.Viewport
    className={cn("relative flex-1 overflow-y-auto", className)}
    role="log"
    {...props}
  />
);

export type ConversationContentProps = ComponentProps<"div">;

export const ConversationContent = ({
  className,
  ...props
}: ConversationContentProps) => (
  <div className={cn("flex flex-col p-4", THREAD_BLOCK_GAP, className)} {...props} />
);

export type ConversationScrollButtonProps = ComponentProps<typeof Button>;

export const ConversationScrollButton = ({
  className,
  ...props
}: ConversationScrollButtonProps) => (
  <ThreadPrimitive.ScrollToBottom asChild>
    <Button
      className={cn(
        "absolute bottom-4 left-[50%] translate-x-[-50%] rounded-full",
        // The primitive disables itself at the bottom of the thread.
        "disabled:pointer-events-none disabled:invisible",
        className,
      )}
      size="icon"
      type="button"
      variant="outline"
      aria-label="Scroll to the latest message"
      {...props}
    >
      <ArrowDownIcon className="size-4" />
    </Button>
  </ThreadPrimitive.ScrollToBottom>
);
