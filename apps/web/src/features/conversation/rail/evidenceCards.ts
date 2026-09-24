import type { EvidenceCard } from "@pathfinder/shared";
import { evidenceCardSchema } from "@pathfinder/shared/generated/zod/evidenceCardSchema";
import { strategyRevisionPayloadSchema } from "@pathfinder/shared/generated/zod/strategyRevisionPayloadSchema";
import type { UIMessage } from "ai";

type Part = UIMessage["parts"][number];

function latestData<T>(
  parts: readonly Part[],
  type: string,
  read: (raw: unknown) => T | null,
): T | null {
  for (let i = parts.length - 1; i >= 0; i--) {
    const part = parts[i];
    if (part?.type !== type || !("data" in part)) continue;
    const found = read(part.data);
    if (found !== null) return found;
  }
  return null;
}

/** The evidence card of the thread's latest check, or null before any check. */
export function latestEvidenceCard(parts: readonly Part[]): EvidenceCard | null {
  return latestData(parts, "data-evidence-card", (raw) => {
    const parsed = evidenceCardSchema.safeParse(raw);
    return parsed.success ? parsed.data : null;
  });
}

/** Whether the strategy changed after the check the card belongs to. */
export function cardIsSuperseded(parts: readonly Part[], card: EvidenceCard): boolean {
  const latest = latestData(parts, "data-strategy-revision", (raw) => {
    const parsed = strategyRevisionPayloadSchema.safeParse(raw);
    return parsed.success ? parsed.data.revision : null;
  });
  return latest !== null && latest !== card.revision;
}

const DOI = /^(?:doi:\s*)?(10\.\d{4,9}\/\S+)$/i;
const PMID = /^(?:pmid:\s*)?(\d{1,9})$/i;
const WEB = /^https?:\/\//i;

/** Where a cited reference opens: a web address, a DOI or a PMID, else nowhere. */
export function referenceHref(reference: string): string | null {
  const text = reference.trim();
  if (WEB.test(text)) return text;
  const doi = DOI.exec(text)?.[1];
  if (doi !== undefined) return `https://doi.org/${doi}`;
  const pmid = PMID.exec(text)?.[1];
  if (pmid !== undefined) return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;
  return null;
}
