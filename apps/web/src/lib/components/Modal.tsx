"use client";

import { Dialog } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "@/lib/utils/cn";

interface ModalProps {
  /** Controls visibility. The modal renders only when `true`. */
  open: boolean;
  /** Called when the user presses Escape, clicks outside, or presses the close button. */
  onClose: () => void;
  /** Optional title rendered as a visually-hidden accessible label. */
  title?: string;
  /** Max-width utility class (default: "max-w-md"). */
  maxWidth?: string;
  /** Whether to show a close (X) button in the top-right corner. */
  showCloseButton?: boolean;
  /** When false, the modal cannot be dismissed by escape, click-outside, or close button. */
  dismissible?: boolean;
  children: React.ReactNode;
}

/**
 * Shared modal shell built on the Radix Dialog primitive.
 *
 * Provides focus trapping, escape-to-close, click-outside-to-close,
 * consistent backdrop, accessible labelling, and enter/exit animations.
 */
export function Modal({
  open,
  onClose,
  title,
  maxWidth = "max-w-md",
  showCloseButton = false,
  dismissible = true,
  children,
}: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => dismissible && !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/50 backdrop-blur-sm data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-full -translate-x-1/2 -translate-y-1/2",
            "max-h-[85vh] flex flex-col",
            "rounded-xl border border-border bg-card p-0 shadow-lg",
            "focus:outline-none",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-scale-out",
            maxWidth,
          )}
          aria-describedby={undefined}
        >
          {title != null && title !== "" && (
            <Dialog.Title className="sr-only">{title}</Dialog.Title>
          )}
          {showCloseButton && dismissible && (
            <Dialog.Close asChild>
              <button
                type="button"
                className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Close"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </Dialog.Close>
          )}
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
