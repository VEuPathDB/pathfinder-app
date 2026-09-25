import { test, expect } from "../fixtures/test";
import { combineId, combineNode } from "../fixtures/ast";

test.describe("Operator change persists to AST", () => {
  test("UI flip UNION->INTERSECT lands in the persisted AST", async ({
    chatPage,
    graphPage,
    sitePicker,
    apiClient,
  }) => {
    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");
    await chatPage.newChat("plasmodb");

    // One planning round -> the two-leaf spec (GenesByText UNION GenesByTaxon).
    await chatPage.send(
      "Build a strategy for P. falciparum 3D7 kinases using InterPro PF00069 and GO terms.",
    );
    await chatPage.expectVerificationFeedback();

    const conversationId = chatPage.lastStrategyId;
    expect(conversationId).toBeTruthy();
    const astUrl = `/api/v1/conversations/${conversationId as string}/ast`;

    // Precondition: the combine starts as UNION in the persisted AST.
    const combine = await combineNode(await apiClient.get(astUrl));
    expect(combine.operator).toBe("UNION");
    const combineStepId = combine.id as string;

    // UI mutation: flip the operator via the edge context menu.
    await graphPage.goToStrategy("plasmodb", conversationId as string);
    await graphPage.expectStrategyTopbar();
    await graphPage.expectNodeVisible(combineStepId);
    await graphPage.changeOperator(combineStepId, "INTERSECT");
    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 30_000 },
    );

    // The persisted AST must now carry INTERSECT - the assertion the
    // flagship journey is missing.
    await expect
      .poll(async () => (await combineNode(await apiClient.get(astUrl))).operator, {
        timeout: 30_000,
      })
      .toBe("INTERSECT");

    // The flip edits the existing combine rather than replacing it.
    expect(await combineId(await apiClient.get(astUrl))).toBe(combineStepId);
  });
});
