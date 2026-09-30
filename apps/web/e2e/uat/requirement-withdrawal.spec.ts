/**
 * A requirement no search states is offered for withdrawal on the question
 * card; dropping it builds the rest, and the facts part shows the requirement
 * retired, never as a gap.
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { storedNodes, siteOrganism } from "../fixtures/site-reads";
import { SIGNAL_PEPTIDE } from "../fixtures/arc-layouts";

/** The card question the dispatch adds for the fold change the arc states. */
const DROP_QUESTION =
  "No search on this site states '2-fold'. Drop it from the request?";
const DROP_OPTION = "Drop 2-fold";
const KEEP_OPTION = "Keep 2-fold";

test.describe("Requirement withdrawal", { tag: "@turn" }, () => {
  test.describe.configure({ timeout: 600_000 });

  test("N14 - A requirement no search states is dropped on the card", async ({
    chatPage,
    apiClient,
    page,
    siteId,
  }) => {
    await chatPage.startOn(siteId);
    const id = chatPage.lastStrategyId ?? "";
    await chatPage.send(
      prompt(
        "withdraw",
        `Find ${siteOrganism(siteId)} genes with a predicted signal peptide, up at least 2-fold.`,
      ),
    );

    const carousel = page.getByTestId("consult-carousel");
    await expect(carousel).toBeVisible({ timeout: 240_000 });
    const slide = carousel.getByTestId("consult-slide");
    await expect(slide).toContainText(DROP_QUESTION);
    const options = slide.locator('[data-testid^="consult-option-"]');
    await expect(options).toHaveCount(2);
    await expect(slide.getByLabel(DROP_OPTION, { exact: true })).toBeVisible();
    await expect(slide.getByLabel(KEEP_OPTION, { exact: true })).toBeVisible();

    await chatPage.answerConsultCarousel();
    const recap = page.getByTestId("consult-recap");
    await expect(recap.getByTestId("consult-recap-question")).toHaveText(
      `Q: ${DROP_QUESTION}`,
      { timeout: 60_000 },
    );
    await expect(recap.getByTestId("consult-recap-answer")).toHaveText(
      `A: ${DROP_OPTION}`,
    );
    await expect
      .poll(
        async () => (await storedNodes(apiClient, id)).map((node) => node.searchName),
        { timeout: 240_000 },
      )
      .toEqual([SIGNAL_PEPTIDE]);

    const withdrawn = chatPage.assistantMessages.filter({
      has: page.locator('[data-testid="facts-retired"][data-kind="withdrawn"]'),
    });
    await expect(withdrawn).toHaveCount(1, { timeout: 240_000 });
    const facts = chatPage.factsIn(withdrawn);
    await expect(
      facts.locator('[data-testid="facts-retired"][data-kind="withdrawn"]'),
    ).toContainText("2-fold");
    await expect(
      facts.locator('[data-testid="facts-gap"]').filter({ hasText: "2-fold" }),
    ).toHaveCount(0);
  });
});
