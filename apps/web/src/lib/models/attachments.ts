import type { ModelCatalogEntry } from "@pathfinder/shared";

// The api holds the same caps and kinds (ai/conversation/attachments.py) and
// refuses a message that breaks them; the composer says so before it is sent.

const MIB = 1024 * 1024;
export const MAX_ATTACHMENT_BYTES = 10 * MIB;
export const MAX_MESSAGE_ATTACHMENT_BYTES = 20 * MIB;
export const MAX_ATTACHMENTS = 6;

export type AttachmentKind = "gene-ids" | "image" | "pdf";

const GENE_ID_EXTENSIONS = [".csv", ".tsv", ".txt"];
const GENE_ID_TYPES = ["text/csv", "text/tab-separated-values", "text/plain"];
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const PDF_TYPE = "application/pdf";

/** The role whose model reads the user's message, per assistant. */
const PROMPT_ROLES: Readonly<Record<string, string>> = {
  pathfinder: "lead",
  site_help: "site_help",
};

interface FileFacts {
  name: string;
  type: string;
}

export function attachmentKind(file: FileFacts): AttachmentKind | null {
  if (IMAGE_TYPES.includes(file.type)) return "image";
  if (file.type === PDF_TYPE) return "pdf";
  const lower = file.name.toLowerCase();
  if (GENE_ID_TYPES.includes(file.type)) return "gene-ids";
  if (GENE_ID_EXTENSIONS.some((ext) => lower.endsWith(ext))) return "gene-ids";
  return null;
}

function reads(model: ModelCatalogEntry, kind: "image" | "pdf"): boolean {
  return kind === "image"
    ? model.supportsImages === true
    : model.supportsDocuments === true;
}

/** The file chooser's accept list: gene-ID lists always, images and PDFs only
 *  when the reader reads them. */
export function acceptFor(model: ModelCatalogEntry | undefined): string {
  const accepted = [...GENE_ID_EXTENSIONS, ...GENE_ID_TYPES];
  if (model !== undefined && reads(model, "image")) accepted.push(...IMAGE_TYPES);
  if (model !== undefined && reads(model, "pdf")) accepted.push(PDF_TYPE);
  return accepted.join(",");
}

/** The files a model reads, as the model catalog lists it, or null for none. */
export function readsLabel(model: ModelCatalogEntry): string | null {
  const kinds = [
    ...(reads(model, "image") ? ["images"] : []),
    ...(reads(model, "pdf") ? ["PDFs"] : []),
  ];
  return kinds.length === 0 ? null : `reads ${kinds.join(" and ")}`;
}

/** The attach button's name: the kinds the reader takes. */
export function attachLabel(model: ModelCatalogEntry | undefined): string {
  const kinds = ["a gene-ID list"];
  if (model !== undefined && reads(model, "image")) kinds.push("an image");
  if (model !== undefined && reads(model, "pdf")) kinds.push("a PDF");
  const last = kinds.pop() ?? "";
  return kinds.length === 0
    ? `Attach ${last}`
    : `Attach ${kinds.join(", ")} or ${last}`;
}

/** Why the reader is offered no images or no PDFs, or null when it reads both. */
export function attachHint(model: ModelCatalogEntry | undefined): string | null {
  if (model === undefined) return null;
  const missing = [
    ...(reads(model, "image") ? [] : ["images"]),
    ...(reads(model, "pdf") ? [] : ["PDFs"]),
  ];
  if (missing.length === 0) return null;
  return (
    `${model.name} does not read ${missing.join(" or ")}; choose a model that ` +
    "does in Settings."
  );
}

/** What the composer says when the file chooser's accept list turned a file
 *  away: why this reader takes no image or PDF, else the kinds read here. */
export function notAcceptedSentence(model: ModelCatalogEntry | undefined): string {
  return (
    attachHint(model) ??
    "PathFinder reads gene-ID lists (.csv, .tsv, .txt), images (PNG, JPEG, " +
      "WebP, GIF) and PDFs."
  );
}

function megabytes(size: number): string {
  return `${(size / MIB).toFixed(1)} MB`;
}

/** Why one file cannot go with the message, or null when it can. The file
 *  chooser's accept list has already turned away a kind the reader does not
 *  read, so only the size is left to refuse. */
export function fileRefusal(file: { name: string; size: number }): string | null {
  if (file.size > MAX_ATTACHMENT_BYTES) {
    return (
      `${file.name} is ${megabytes(file.size)}; one attachment can be at most ` +
      `${MAX_ATTACHMENT_BYTES / MIB} MB.`
    );
  }
  return null;
}

/** Why the attachments of one message cannot go together, or null. */
export function messageRefusal(sizes: readonly number[]): string | null {
  if (sizes.length > MAX_ATTACHMENTS) {
    return (
      `One message can carry at most ${MAX_ATTACHMENTS} attachments; ` +
      `this one has ${sizes.length}.`
    );
  }
  const total = sizes.reduce((sum, size) => sum + size, 0);
  if (total > MAX_MESSAGE_ATTACHMENT_BYTES) {
    return (
      `These attachments come to ${megabytes(total)}; one message can carry ` +
      `at most ${MAX_MESSAGE_ATTACHMENT_BYTES / MIB} MB.`
    );
  }
  return null;
}

/** The model that reads the user's message: the pick for the reading role,
 *  else the deployment's default for it. */
export function readerModel(
  assistantId: string,
  picks: Readonly<Record<string, string>>,
  defaults: Readonly<Record<string, string>>,
  catalog: readonly ModelCatalogEntry[],
): ModelCatalogEntry | undefined {
  const role = PROMPT_ROLES[assistantId] ?? assistantId;
  const modelId = picks[role] ?? defaults[role];
  return catalog.find((m) => m.id === modelId);
}
