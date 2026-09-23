import { z } from "zod";

import { edaFilterSchema } from "@pathfinder/shared/generated/zod/edaFilterSchema";

import { filterSummary } from "@/lib/eda/filterSummary";

/** The parameter every EDA-backed WDK search declares for its analysis spec. */
export const EDA_ANALYSIS_SPEC_PARAM = "eda_analysis_spec";

const edaAnalysisSpecSchema = z.object({
  studyId: z.string().min(1),
  displayName: z.string().default(""),
  descriptor: z.object({
    subset: z.object({ descriptor: z.array(edaFilterSchema) }),
    computations: z.array(z.unknown()).default([]),
  }),
});

export interface EdaSpecSummary {
  displayName: string;
  studyId: string;
  filters: string[];
  computationCount: number;
}

export type EdaSpecParse =
  { ok: true; compact: string; summary: EdaSpecSummary } | { ok: false; error: string };

/** Validate the editor text as an analysis spec, or say what is wrong. */
export function parseEdaSpec(text: string): EdaSpecParse {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (err) {
    const reason = err instanceof SyntaxError ? err.message : String(err);
    return { ok: false, error: `Not valid JSON: ${reason}` };
  }
  const parsed = edaAnalysisSpecSchema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const where = issue?.path.map(String).join(".") ?? "";
    return {
      ok: false,
      error: `${where === "" ? "spec" : where}: ${issue?.message ?? "invalid"}`,
    };
  }
  const spec = parsed.data;
  return {
    ok: true,
    compact: JSON.stringify(raw),
    summary: {
      displayName: spec.displayName,
      studyId: spec.studyId,
      filters: spec.descriptor.subset.descriptor.map(
        (filter) => `${filter.variableId}: ${filterSummary(filter)}`,
      ),
      computationCount: spec.descriptor.computations.length,
    },
  };
}

/** The stored value indented for editing; text that is not JSON stays as it is. */
export function prettyEdaSpec(value: string): string {
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}
