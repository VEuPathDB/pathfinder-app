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

/**
 * The control sits on a rail of its own between the viewport and the composer,
 * so it stays above the composer instead of scrolling with the thread. The
 * rail has no height, so it takes no room from either.
 */
export const ConversationScrollButton = ({
  className,
  ...props
}: ConversationScrollButtonProps) => (
  <div data-testid="conversation-scroll-rail" className="relative z-10 h-0">
    <ThreadPrimitive.ScrollToBottom asChild>
      <Button
        className={cn(
          "absolute bottom-2 left-[50%] translate-x-[-50%] rounded-full shadow-md",
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
  </div>
);
