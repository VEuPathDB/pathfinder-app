import type {
  AttachmentAdapter,
  CompleteAttachment,
  PendingAttachment,
  ThreadUserMessagePart,
} from "@assistant-ui/react";
import type { ModelCatalogEntry } from "@pathfinder/shared";

import { acceptFor, attachmentKind, fileRefusal } from "@/lib/models/attachments";
import { parseGeneCsv } from "@/lib/utils/parseGeneCsv";

const OPAQUE = 255;
const WHITE = 255;

function dataUrl(blob: Blob, name: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error(`Could not read ${name}.`));
    reader.readAsDataURL(blob);
  });
}

/** Composite every pixel over white. False when no pixel is transparent. */
function flattenOnWhite(rgba: Uint8ClampedArray): boolean {
  let changed = false;
  for (let pixel = 0; pixel < rgba.length; pixel += 4) {
    const alpha = rgba[pixel + 3] ?? OPAQUE;
    if (alpha === OPAQUE) continue;
    for (let channel = pixel; channel < pixel + 3; channel++) {
      const value = rgba[channel] ?? 0;
      rgba[channel] = (value * alpha + WHITE * (OPAQUE - alpha)) / OPAQUE;
    }
    rgba[pixel + 3] = OPAQUE;
    changed = true;
  }
  return changed;
}

/**
 * The image as a model reads it: a model reads a transparent pixel as black,
 * so an image with transparent pixels is drawn on white and sent as a PNG.
 */
async function withoutTransparency(file: File, name: string): Promise<Blob> {
  if (file.type === "image/jpeg") return file;
  const unreadable = `Could not read ${name} as an image.`;
  const bitmap = await createImageBitmap(file).catch((cause: unknown) => {
    throw new Error(unreadable, { cause });
  });
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const context = canvas.getContext("2d");
  if (context === null) throw new Error(unreadable);
  context.drawImage(bitmap, 0, 0);
  bitmap.close();
  const image = context.getImageData(0, 0, canvas.width, canvas.height);
  if (!flattenOnWhite(image.data)) return file;
  context.putImageData(image, 0, 0);
  return canvas.convertToBlob({ type: "image/png" });
}

async function geneIdText(file: File, name: string): Promise<ThreadUserMessagePart> {
  const ids = parseGeneCsv(await file.text());
  // Plain framing, so input screening reads the ids as a list.
  const text =
    ids.length > 0
      ? `Attached gene-ID list from ${name}: ${ids.join(", ")}`
      : `Attached file ${name} contained no recognizable gene IDs.`;
  return { type: "text", text };
}

/**
 * A gene-ID list goes to the model as text the tools can read. An image or a
 * PDF goes inline as a file part, and only when the model that reads the
 * message reads that kind. An image with transparent pixels goes on white.
 */
export class ChatAttachmentAdapter implements AttachmentAdapter {
  accept: string;

  constructor(reader: ModelCatalogEntry | undefined) {
    this.accept = acceptFor(reader);
  }

  async add({ file }: { file: File }): Promise<PendingAttachment> {
    const refusal = fileRefusal(file);
    if (refusal !== null) throw new Error(refusal);
    return {
      id: crypto.randomUUID(),
      type: attachmentKind(file) === "image" ? "image" : "document",
      name: file.name,
      contentType: file.type,
      file,
      status: { type: "requires-action", reason: "composer-send" },
    };
  }

  async send(attachment: PendingAttachment): Promise<CompleteAttachment> {
    const { file, name } = attachment;
    const kind = attachmentKind(file);
    const content: ThreadUserMessagePart =
      kind === "image"
        ? {
            type: "image",
            image: await dataUrl(await withoutTransparency(file, name), name),
            filename: name,
          }
        : kind === "pdf"
          ? {
              type: "file",
              data: await dataUrl(file, name),
              mimeType: file.type,
              filename: name,
            }
          : await geneIdText(file, name);
    return { ...attachment, status: { type: "complete" }, content: [content] };
  }

  async remove(): Promise<void> {}
}
