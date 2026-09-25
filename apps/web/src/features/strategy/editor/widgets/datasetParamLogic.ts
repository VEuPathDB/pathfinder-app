import { z } from "zod";

const DatasetIdListContent = z.object({ ids: z.array(z.string()).default([]) });
const DatasetBasketContent = z.object({ basketName: z.string().default("") });
const DatasetStrategyContent = z.object({
  strategyId: z.union([z.string(), z.number()]).transform(String),
});

const DatasetConfigSchema = z.discriminatedUnion("sourceType", [
  z.object({ sourceType: z.literal("idList"), sourceContent: DatasetIdListContent }),
  z.object({ sourceType: z.literal("basket"), sourceContent: DatasetBasketContent }),
  z.object({
    sourceType: z.literal("strategy"),
    sourceContent: DatasetStrategyContent,
  }),
]);

export type DatasetConfig = z.infer<typeof DatasetConfigSchema>;

export type DatasetWidgetTab = "paste" | "default" | "upload" | "basket" | "strategy";

export function decodeDatasetValue(raw: string): DatasetConfig | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    const result = DatasetConfigSchema.safeParse(parsed);
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}

export function encodeDatasetValue(config: DatasetConfig | null): string {
  if (config === null) return "";
  return JSON.stringify(config);
}

export function parseIdsFromText(text: string): string[] {
  return text
    .split(/[\n,]+/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

export function initialTabFor(
  config: DatasetConfig | null,
  hasDefault: boolean,
): DatasetWidgetTab {
  if (config === null) return hasDefault ? "default" : "paste";
  if (config.sourceType === "idList") return "paste";
  if (config.sourceType === "basket") return "basket";
  return "strategy";
}

export function pasteTextFromConfig(config: DatasetConfig | null): string {
  if (config === null) return "";
  if (config.sourceType !== "idList") return "";
  return config.sourceContent.ids.join("\n");
}

export function basketNameFromConfig(config: DatasetConfig | null): string {
  if (config === null) return "";
  if (config.sourceType !== "basket") return "";
  return config.sourceContent.basketName;
}

export function strategyIdFromConfig(config: DatasetConfig | null): string {
  if (config === null) return "";
  if (config.sourceType !== "strategy") return "";
  return config.sourceContent.strategyId;
}

export function defaultIdListFromInitial(initial: unknown): string[] {
  if (typeof initial !== "string") return [];
  try {
    const parsed = JSON.parse(initial) as unknown;
    const result = DatasetConfigSchema.safeParse(parsed);
    if (result.success && result.data.sourceType === "idList") {
      return result.data.sourceContent.ids;
    }
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
