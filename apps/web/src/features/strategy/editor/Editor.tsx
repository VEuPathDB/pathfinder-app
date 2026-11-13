"use client";

import { useRef } from "react";
import type { Step } from "@strategist/shared";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { QueryBoundary } from "@/lib/components/QueryBoundary";
import { EditorContent, type CloseHandler } from "./EditorContent";

interface EditorProps {
  step: Step | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  siteId: string;
  recordType: string | null;
  conversationId: string;
}

export function Editor({
  step,
  isOpen,
  onOpenChange,
  siteId,
  recordType,
  conversationId,
}: EditorProps) {
  const closeHandlerRef = useRef<CloseHandler | null>(null);

  const handleSheetOpenChange = (open: boolean): void => {
    if (open) {
      onOpenChange(true);
      return;
    }
    const handler = closeHandlerRef.current;
    if (handler === null) {
      onOpenChange(false);
      return;
    }
    void (async () => {
      await handler();
    })();
  };

  return (
    <Sheet open={isOpen} onOpenChange={handleSheetOpenChange}>
      <SheetContent
        side="right"
        data-testid="step-editor-sheet"
        className="flex w-[440px] flex-col gap-0 p-0 sm:max-w-[440px]"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>Edit step</SheetTitle>
          <SheetDescription>
            Edit parameters for the selected strategy step.
          </SheetDescription>
        </SheetHeader>
        {step !== null && (
          <QueryBoundary>
            <EditorContent
              key={step.id}
              step={step}
              siteId={siteId}
              recordType={recordType}
              conversationId={conversationId}
              registerCloseHandler={(h) => {
                closeHandlerRef.current = h;
              }}
              onClosed={() => {
                closeHandlerRef.current = null;
                onOpenChange(false);
              }}
            />
          </QueryBoundary>
        )}
      </SheetContent>
    </Sheet>
  );
}
