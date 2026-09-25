/**
 * The EDA route fixtures must satisfy the generated wire schemas.
 *
 * A recorded payload that the app would reject is a fixture that proves
 * nothing, and the SSE part path does no validation of its own, so a bad part
 * payload is invisible in a journey. This file parses every fixture the
 * journeys serve. It uses the bare Playwright runner, not `../fixtures/test`,
 * because that fixture set carries an auto-use cleanup that logs in and clears
 * server state: a schema check must not depend on a running API.
 */

import { test, expect } from "@playwright/test";
import type { ZodType } from "zod";
import { conversationEdaResponseSchema } from "@pathfinder/shared/generated/zod/conversationEdaResponseSchema";
import { conversationResponseSchema } from "@pathfinder/shared/generated/zod/conversationResponseSchema";
import { edaAnalysisPatchResponseSchema } from "@pathfinder/shared/generated/zod/edaAnalysisPatchResponseSchema";
import { edaAnalysisStateSchema } from "@pathfinder/shared/generated/zod/edaAnalysisStateSchema";
import { edaStudyListResponseSchema } from "@pathfinder/shared/generated/zod/edaStudyListResponseSchema";
import { edaSubsetPreviewPartSchema } from "@pathfinder/shared/generated/zod/edaSubsetPreviewPartSchema";
import { edaVizPartSchema } from "@pathfinder/shared/generated/zod/edaVizPartSchema";
import { edaVizResponseSchema } from "@pathfinder/shared/generated/zod/edaVizResponseSchema";

import {
  analysisState,
  COMPARED_ANALYSIS,
  exportedStrategy,
  FILTERED_ANALYSIS,
  STUDY_ROW,
  SUBSET_PREVIEW,
  VOLCANO_RESPONSE,
  VOLCANO_VIZ,
} from "../fixtures/eda";

const CONVERSATION_ID = "11111111-2222-4333-8444-555555555555";

interface Case {
  name: string;
  schema: ZodType<unknown>;
  payload: unknown;
}

const CASES: Case[] = [
  {
    name: "GET /eda/studies",
    schema: edaStudyListResponseSchema,
    payload: { studies: [STUDY_ROW] },
  },
  {
    name: "POST /eda/viz",
    schema: edaVizResponseSchema,
    payload: VOLCANO_RESPONSE,
  },
  {
    name: "GET /conversations/{id}/eda, unbound",
    schema: conversationEdaResponseSchema,
    payload: { analysis: null },
  },
  {
    name: "GET /conversations/{id}/eda, bound",
    schema: conversationEdaResponseSchema,
    payload: { analysis: FILTERED_ANALYSIS },
  },
  {
    name: "GET /conversations/{id}/eda, compared",
    schema: conversationEdaResponseSchema,
    payload: { analysis: COMPARED_ANALYSIS },
  },
  {
    name: "data-eda.analysis-state, unfiltered",
    schema: edaAnalysisStateSchema,
    payload: analysisState(),
  },
  {
    name: "data-eda.analysis-state, filtered",
    schema: edaAnalysisStateSchema,
    payload: FILTERED_ANALYSIS,
  },
  {
    name: "data-eda.analysis-state, after a compute",
    schema: edaAnalysisStateSchema,
    payload: COMPARED_ANALYSIS,
  },
  {
    name: "data-eda.subset-preview",
    schema: edaSubsetPreviewPartSchema,
    payload: SUBSET_PREVIEW,
  },
  { name: "data-eda.viz", schema: edaVizPartSchema, payload: VOLCANO_VIZ },
  {
    name: "PATCH /conversations/{id}/eda, bind",
    schema: edaAnalysisPatchResponseSchema,
    payload: { analysis: analysisState(), step: null },
  },
  {
    name: "PATCH /conversations/{id}/eda, export-step",
    schema: edaAnalysisPatchResponseSchema,
    payload: {
      analysis: { ...COMPARED_ANALYSIS, revision: 3 },
      step: exportedStrategy(CONVERSATION_ID),
    },
  },
  {
    name: "the exported strategy the tab parses back",
    schema: conversationResponseSchema,
    payload: exportedStrategy(CONVERSATION_ID),
  },
];

test.describe("EDA fixtures conform to the wire schemas", () => {
  for (const entry of CASES) {
    test(`${entry.name} parses`, () => {
      const result = entry.schema.safeParse(entry.payload);
      const issues = result.success
        ? ""
        : result.error.issues
            .map((issue) => `${issue.path.join(".")}: ${issue.message}`)
            .join("; ");
      expect(result.success, `${entry.name} failed the wire schema: ${issues}`).toBe(
        true,
      );
    });
  }
});
