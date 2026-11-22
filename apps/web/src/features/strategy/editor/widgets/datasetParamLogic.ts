import { WDKDatasetConfigIdListSchema } from "@strategist/shared/generated/zod/WDKDatasetConfigIdListSchema";

export type DatasetWidgetTab = "paste" | "default" | "upload" | "basket" | "strategy";

export function parseIdsFromText(text: string): string[] {
  return text
    .split(/[\n,]+/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

export function defaultIdListFromInitial(initial: unknown): string[] {
  if (typeof initial !== "string") return [];
  try {
    const parsed = JSON.parse(initial) as unknown;
    const result = WDKDatasetConfigIdListSchema.safeParse(parsed);
    if (result.success) return result.data.sourceContent.ids;
    if (Array.isArray(parsed)) {
      return parsed
        .map((entry) => (typeof entry === "string" ? entry : null))
        .filter((entry): entry is string => entry !== null);
    }
    return [];
  } catch {
    return parseIdsFromText(initial);
  }
}
