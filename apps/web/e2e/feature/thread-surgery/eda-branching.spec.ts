/**
 * Branching a thread that has an EDA study open.
 *
 * The binding, the analysis and its subset are the real service's: the subset
 * is written on the site, as a researcher edits it there, and the tab reads it
 * back from `GET /conversations/{id}/eda`. A branch holds an analysis of its
 * own, so what it opens never reaches its parent.
 */

import type { APIRequestContext } from "@playwright/test";
import type { SiteResponse } from "@pathfinder/shared";

import { test, expect } from "../../fixtures/test";
import { DATASET_ID, FEBRILE_FILTER, SITE_ID, STUDY_TITLE } from "../../fixtures/eda";
import { siteRow } from "../../fixtures/site-reads";
import { wdkTestToken } from "../../fixtures/wdk-account";

const OPEN_TURN = "show me heat shock genes";
const FILTER_CHIP = "eda-filter-chip-0";

/** The plain echo reply for `text`, which calls no tool. */
function echoOf(text: string): RegExp {
  return new RegExp(`\\[mock\\] ${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`);
}

/** Write the analysis's subset through the site's own EDA service. */
async function setSubsetOnTheSite(
  request: APIRequestContext,
  site: SiteResponse,
  analysisId: string,
  filters: unknown[],
): Promise<void> {
  const headers = { Cookie: `Authorization=${wdkTestToken()}` };
  const me = await request.get(`${site.baseUrl}/users/current`, { headers });
  expect(me.status(), "users/current").toBe(200);
  const { id } = (await me.json()) as { id: number };
  const origin = new URL(site.baseUrl).origin;
  const url = `${origin}/eda/users/${String(id)}/analyses/${site.projectId}/${analysisId}`;
  const read = await request.get(url, { headers });
  expect(read.status(), "analysis read").toBe(200);
  const { descriptor } = (await read.json()) as {
    descriptor: { subset: Record<string, unknown> } & Record<string, unknown>;
  };
  const written = await request.patch(url, {
    headers: { ...headers, "Content-Type": "application/json" },
    data: {
      descriptor: {
        ...descriptor,
        subset: { ...descriptor.subset, descriptor: filters },
      },
    },
  });
  expect(written.ok(), `analysis write ${written.status()}`).toBe(true);
}

interface AnalysisRead {
  analysis: {
    analysisId: string;
    studyDisplayName: string;
    numFilters: number;
  } | null;
}

test.describe("Branching a thread with a study open", () => {
  // Each journey drives three to five turns through the worker, and one queued
  // behind another suite's build waits minutes.
  test.describe.configure({ timeout: 600_000 });

  test("a branch opens its own analysis and leaves the parent's site subset alone", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    await chatPage.startOn(SITE_ID);

    await chatPage.sendTurn(OPEN_TURN, echoOf(OPEN_TURN));
    const parentId = chatPage.lastStrategyId as string;

    // Open a study on the thread, then narrow its subset on the site.
    const bound = await apiClient.patch(`/api/v1/conversations/${parentId}/eda`, {
      data: { action: "bind", siteId: SITE_ID, datasetId: DATASET_ID },
    });
    expect(bound.status(), `bind ${await bound.text()}`).toBe(200);
    const parentBound = (await bound.json()) as AnalysisRead;
    const parentAnalysisId = parentBound.analysis?.analysisId ?? "";
    expect(parentAnalysisId).not.toBe("");
    expect(parentBound.analysis?.studyDisplayName).toBe(STUDY_TITLE);

    const site = await siteRow(apiClient, SITE_ID);
    await setSubsetOnTheSite(page.request, site, parentAnalysisId, [FEBRILE_FILTER]);
    const reread = await apiClient.get(`/api/v1/conversations/${parentId}/eda`);
    expect(((await reread.json()) as AnalysisRead).analysis?.numFilters).toBe(1);

    // The parent's tab reads the site's subset.
    await page.goto(`/${SITE_ID}/conversation/${parentId}/eda`);
    await expect(page.getByTestId("eda-workbench-title")).toContainText(STUDY_TITLE, {
      timeout: 60_000,
    });
    await expect(page.getByTestId(FILTER_CHIP)).toContainText("febrile", {
      timeout: 60_000,
    });

    // Branch from the thread.
    await page.goto(`/${SITE_ID}/conversation/${parentId}`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    const branchId = await chatPage.branchFromAssistantReply(echoOf(OPEN_TURN));
    expect(branchId).not.toBe(parentId);

    // The branch opens the same study on an analysis of its own.
    const branchBound = await apiClient.patch(`/api/v1/conversations/${branchId}/eda`, {
      data: { action: "bind", siteId: SITE_ID, datasetId: DATASET_ID },
    });
    expect(branchBound.status(), `branch bind ${await branchBound.text()}`).toBe(200);
    const branchAnalysis = ((await branchBound.json()) as AnalysisRead).analysis;
    expect(branchAnalysis?.studyDisplayName).toBe(STUDY_TITLE);
    expect(branchAnalysis?.numFilters).toBe(0);
    expect(branchAnalysis?.analysisId).not.toBe(parentAnalysisId);

    // The branch's own study card renders, with no filter of the parent's.
    await page.goto(`/${SITE_ID}/conversation/${branchId}/eda`);
    await expect(page.getByTestId("eda-workbench-title")).toContainText(STUDY_TITLE, {
      timeout: 60_000,
    });
    await expect(page.getByTestId(FILTER_CHIP)).toHaveCount(0);

    // The parent is untouched, on the wire and on the tab.
    const parentAfter = await apiClient.get(`/api/v1/conversations/${parentId}/eda`);
    const parentState = ((await parentAfter.json()) as AnalysisRead).analysis;
    expect(parentState?.analysisId).toBe(parentAnalysisId);
    expect(parentState?.numFilters).toBe(1);

    await page.goto(`/${SITE_ID}/conversation/${parentId}/eda`);
    await expect(page.getByTestId("eda-workbench-title")).toContainText(STUDY_TITLE, {
      timeout: 60_000,
    });
    await expect(page.getByTestId(FILTER_CHIP)).toContainText("febrile", {
      timeout: 60_000,
    });
  });
});
