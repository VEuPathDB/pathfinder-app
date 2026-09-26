/**
 * The candidate drug-targets journey: a vague request asks first and builds
 * from the answers, a second build request leaves the strategy standing, a
 * step is added, the operator is flipped on the canvas, and a question about
 * the flip changes nothing.
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { LAYOUTS, SIGNAL_PEPTIDE, layoutOf } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readConversation, readNodes, siteOrganism } from "../fixtures/site-reads";
import {
  combineWith,
  expectCanvasSaved,
  nodeById,
  openCanvas,
} from "../fixtures/strategy-builds";

test.describe("Candidate drug-targets journey", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 900_000 });

  test("vague request -> questions and a build -> second build -> add a step -> canvas flip -> impact", async ({
    chatPage,
    graphPage,
    apiClient,
    page,
    siteId,
  }) => {
    const organism = siteOrganism(siteId);
    await chatPage.startOn(siteId);

    await chatPage.send(
      prompt(
        "consult",
        `I want to find candidate drug targets in ${organism}: genes that are expressed, do not vary much, and have no human equivalent.`,
      ),
    );
    await chatPage.answerConsultCarousel();
    await chatPage.expectIdle(240_000);
    await expect(page.getByTestId("consult-recap")).toContainText("Your answers");

    const id = chatPage.lastStrategyId ?? "";
    await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
    const signalStep = (await readConversation(apiClient, id)).steps?.find(
      (step) => step.searchName === SIGNAL_PEPTIDE,
    );
    expect(signalStep?.wdkStepId ?? 0).toBeGreaterThan(0);

    await chatPage.sendAndSettle(
      prompt("second-build", `Build a strategy for ${organism} protein kinases.`),
    );
    expect(layoutOf(await readNodes(apiClient, id))).toEqual(LAYOUTS.single);
    const afterSecond = (await readConversation(apiClient, id)).steps ?? [];
    expect(afterSecond.map((step) => step.wdkStepId)).toEqual([signalStep?.wdkStepId]);

    await chatPage.sendAndSettle(
      prompt(
        "add-step",
        "Also keep only those predicted to be exported to the host cell.",
      ),
    );
    await expect
      .poll(async () => layoutOf(await readNodes(apiClient, id)).operators, {
        timeout: 60_000,
      })
      .toEqual(["INTERSECT"]);

    const combineId = combineWith(await readNodes(apiClient, id), "INTERSECT").id ?? "";
    await openCanvas(graphPage, siteId, id);
    await graphPage.expectNodeVisible(combineId);
    await graphPage.changeOperator(combineId, "UNION");
    await expectCanvasSaved(graphPage);
    await expect
      .poll(async () => nodeById(await readNodes(apiClient, id), combineId).operator, {
        timeout: 30_000,
      })
      .toBe("UNION");
    await graphPage.strategyPageBackButton.click();
    await graphPage.expectOnChatRoute(id);

    const flipped = await readConversation(apiClient, id);
    await chatPage.sendAndSettle(
      prompt("impact", "What is the impact of switching the combine to UNION?"),
    );
    expect(layoutOf(await readNodes(apiClient, id)).operators).toEqual(["UNION"]);
    const asked = await readConversation(apiClient, id);
    expect((asked.steps ?? []).map((step) => step.wdkStepId)).toEqual(
      (flipped.steps ?? []).map((step) => step.wdkStepId),
    );
  });
});
