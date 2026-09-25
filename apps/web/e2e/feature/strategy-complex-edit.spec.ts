import { test, expect } from "../fixtures/test";
import { combineNode, leafBySearch } from "../fixtures/ast";

test.describe("Complex combine strategy - multi-edit via UI", () => {
  test("build 3-step combine, flip operator + edit a leaf param, both persist + sync, model answers", async ({
    chatPage,
    graphPage,
    sitePicker,
    apiClient,
  }) => {
    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");
    await chatPage.newChat("plasmodb");

    await chatPage.send(
      "Build a strategy for P. falciparum 3D7 kinases using InterPro PF00069 and GO terms.",
    );
    await chatPage.expectVerificationFeedback();

    const conversationId = chatPage.lastStrategyId as string;
    const astUrl = `/api/v1/conversations/${conversationId}/ast`;

    const combine = await combineNode(await apiClient.get(astUrl));
    expect(combine.operator).toBe("UNION");
    const combineStepId = combine.id as string;

    const leaf = await leafBySearch(await apiClient.get(astUrl), "GenesByText");
    expect(leaf.parameters?.["text_expression"]?.value).toBe("kinase");
    const leafId = leaf.id as string;

    await chatPage.send("how many genes are in this combined strategy?");
    await chatPage.expectAssistantMessage(/\[mock\]/i, { timeout: 60_000 });
    await chatPage.expectIdle();

    await graphPage.goToStrategy("plasmodb", conversationId);
    await graphPage.expectStrategyTopbar();

    await graphPage.changeOperator(combineStepId, "INTERSECT");
    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 30_000 },
    );
    await expect
      .poll(async () => (await combineNode(await apiClient.get(astUrl))).operator, {
        timeout: 30_000,
      })
      .toBe("INTERSECT");

    await graphPage.clickNode(leafId);
    await expect(graphPage.editorSheet).toBeVisible({ timeout: 20_000 });
    const textInput = graphPage.editorSheet.locator('input[name="text_expression"]');
    await expect(textInput).toHaveValue("kinase");
    await textInput.fill("phosphatase");
    const save = graphPage.editorSheet.getByTestId("step-editor-save");
    await expect(save).toBeVisible({ timeout: 15_000 });
    await save.click();
    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 30_000 },
    );

    // Both edits survive together: the param change did not revert the operator.
    await expect
      .poll(
        async () =>
          (await leafBySearch(await apiClient.get(astUrl), "GenesByText")).parameters?.[
            "text_expression"
          ]?.value,
        { timeout: 30_000 },
      )
      .toBe("phosphatase");
    expect((await combineNode(await apiClient.get(astUrl))).operator).toBe("INTERSECT");
  });
});
