"use client";

import {
  AttachmentPrimitive,
  ComposerPrimitive,
  useAui,
  useAuiEvent,
  useAuiState,
} from "@assistant-ui/react";
import { FileText, ImageIcon, Paperclip, X } from "lucide-react";
import { useRef } from "react";
import { toast } from "sonner";

import {
  acceptFor,
  attachHint,
  attachLabel,
  messageRefusal,
  notAcceptedSentence,
} from "@/lib/models/attachments";
import { useReaderModel } from "@/features/conversation/runtime/useReaderModel";

function AttachmentChip({ image }: { image: boolean }) {
  const Icon = image ? ImageIcon : FileText;
  return (
    <div
      data-testid="composer-attachment"
      className="flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs"
    >
      <Icon className="size-3 shrink-0 text-muted-foreground" aria-hidden />
      <span className="max-w-[12rem] truncate">
        <AttachmentPrimitive.Name />
      </span>
      <AttachmentPrimitive.Remove
        aria-label="Remove attachment"
        className="ml-0.5 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
      >
        <X className="size-3" />
      </AttachmentPrimitive.Remove>
    </div>
  );
}

/** Why the composer's attachments cannot go together, or null when they can. */
export function useAttachmentRefusal(): string | null {
  const attachments = useAuiState((s) => s.composer.attachments);
  return messageRefusal(attachments.map((a) => a.file?.size ?? 0));
}

export function ComposerAttachmentList({
  assistantId,
  refusal,
}: {
  assistantId: string;
  refusal: string | null;
}) {
  const count = useAuiState((s) => s.composer.attachments.length);
  const { reader } = useReaderModel(assistantId);
  useAuiEvent("composer.attachmentAddError", ({ reason, message }) =>
    toast.error(reason === "not-accepted" ? notAcceptedSentence(reader) : message),
  );
  if (count === 0) return null;
  return (
    <div className="flex flex-col gap-1 px-2 pt-2">
      <div className="flex flex-wrap gap-1.5">
        <ComposerPrimitive.Attachments>
          {({ attachment }) => <AttachmentChip image={attachment.type === "image"} />}
        </ComposerPrimitive.Attachments>
      </div>
      {refusal !== null && (
        <p role="alert" className="text-xs text-destructive">
          {refusal}
        </p>
      )}
    </div>
  );
}

/**
 * The chooser takes its accept list from the current reader: the runtime's
 * composer state keeps the list it read first when the model changes.
 */
export function AttachButton({ assistantId }: { assistantId: string }) {
  const { reader } = useReaderModel(assistantId);
  const aui = useAui();
  const chooser = useRef<HTMLInputElement>(null);
  const hint = attachHint(reader);

  function attach(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      // A refused file reaches the researcher through composer.attachmentAddError.
      aui
        .composer()
        .addAttachment(file)
        .catch(() => undefined);
    }
  }

  return (
    <>
      <input
        ref={chooser}
        type="file"
        multiple
        hidden
        accept={acceptFor(reader)}
        onChange={(event) => {
          attach(event.currentTarget.files);
          event.currentTarget.value = "";
        }}
      />
      <button
        type="button"
        data-testid="add-attachment"
        aria-label={attachLabel(reader)}
        title={hint ?? attachLabel(reader)}
        onClick={() => chooser.current?.click()}
        className="inline-flex items-center gap-1.5 rounded-md border border-input px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
      >
        <Paperclip className="h-4 w-4" /> Attach
      </button>
    </>
  );
}
