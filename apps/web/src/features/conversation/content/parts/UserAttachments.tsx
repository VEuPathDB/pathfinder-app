"use client";

import { MessagePrimitive, type CompleteAttachment } from "@assistant-ui/react";
import { FileText } from "lucide-react";
import Image from "next/image";

function UserAttachment({ attachment }: { attachment: CompleteAttachment }) {
  const [part] = attachment.content;
  if (part?.type === "image") {
    return (
      <Image
        src={part.image}
        alt={attachment.name}
        width={256}
        height={160}
        unoptimized
        data-testid="user-attachment-image"
        className="h-auto max-h-40 w-auto max-w-[16rem] rounded-md border border-border object-contain"
      />
    );
  }
  return (
    <span
      data-testid="user-attachment-file"
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs"
    >
      <FileText className="size-3 shrink-0 text-muted-foreground" aria-hidden />
      <span className="max-w-[14rem] truncate">{attachment.name}</span>
    </span>
  );
}

/** The images and documents a user message carries, drawn above its text. */
export function UserAttachments() {
  return (
    <div className="flex flex-wrap justify-end gap-2 empty:hidden">
      <MessagePrimitive.Attachments>
        {({ attachment }) => <UserAttachment attachment={attachment} />}
      </MessagePrimitive.Attachments>
    </div>
  );
}
