import { test, expect } from "../fixtures/test";
import { signInAsWdkAccount } from "../fixtures/wdk-account";
import {
  COMBINE_SEARCH_NAME,
  astNodes,
  combineOperators,
  leafBySearch,
  leafIdBySearch,
} from "../fixtures/ast";

test.describe("Comprehensive multi-param strategy lifecycle", () => {
  test.use({ viewport: { width: 1680, height: 900 } });

  test("scoping -> build 5-step all-param strategy -> verify -> optimize -> edit every param type -> operator flip -> delete -> Q&A", async ({
    page,
    chatPage,
    graphPage,
    sitePicker,
  }) => {
    await signInAsWdkAccount(page.context().request, "plasmodb");

    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");
    await chatPage.newChat("plasmodb");

    await chatPage.send(
      "I'm studying P. falciparum kinases - how strict on 'doesn't vary much' should I be?",
    );
    await chatPage.expectClarifyingQuestions();

    await chatPage.send(
      "Build a comprehensive kinase strategy with all parameter types.",
    );
    await chatPage.expectVerificationSuccess();
    await chatPage.expectIdle();

    const conversationId = chatPage.lastStrategyId as string;
    const astUrl = `/api/v1/conversations/${conversationId}/ast`;

    const built = await astNodes(await page.request.get(astUrl));
    expect(built).toHaveLength(5);
    expect(built.map((n) => n.searchName).sort()).toEqual([
      "GenesByGoTerm",
      "GenesByTaxon",
      "GenesByText",
      COMBINE_SEARCH_NAME,
      COMBINE_SEARCH_NAME,
    ]);
    expect(await combineOperators(await page.request.get(astUrl))).toEqual([
      "INTERSECT",
      "UNION",
    ]);
    const goLeaf = await leafBySearch(await page.request.get(astUrl), "GenesByGoTerm");
    expect(goLeaf.parameters?.["go_term_evidence"]?.values).toEqual([
      "Curated",
      "Computed",
    ]);
    const textLeafId = await leafIdBySearch(
      await page.request.get(astUrl),
      "GenesByText",
    );
    const taxonLeafId = await leafIdBySearch(
      await page.request.get(astUrl),
      "GenesByTaxon",
    );
    const goLeafId = goLeaf.id as string;
    // The UNION branch feeds the INTERSECT, rather than chaining left to right.
    const union = built.find(
      (n) => n.searchName === COMBINE_SEARCH_NAME && n.operator === "UNION",
    );
    expect([union?.primaryInput?.id, union?.secondaryInput?.id].sort()).toEqual(
      [textLeafId, goLeafId].sort(),
    );
    const unionId = union?.id as string;

    await graphPage.goToStrategy("plasmodb", conversationId);
    await graphPage.expectStrategyTopbar();
    await graphPage.expectNodeCount(5);

    await graphPage.clickNode(textLeafId);
    await graphPage.expectEditorSheetOpen();
    const textInput = graphPage.editorSheet.locator('input[name="text_expression"]');
    await expect(textInput).toHaveValue("kinase");
    await textInput.fill("phosphatase");
    await graphPage.saveEditor();
    await expect
      .poll(
        async () =>
          (await leafBySearch(await page.request.get(astUrl), "GenesByText"))
            .parameters?.["text_expression"]?.value,
        { timeout: 30_000 },
      )
      .toBe("phosphatase");

    await graphPage.clickNode(goLeafId);
    await graphPage.expectEditorSheetOpen();
    await graphPage.expandEditorAdvanced();
    await graphPage.toggleEditorCheckbox("Computed");
    await graphPage.saveEditor();
    await expect
      .poll(
        async () =>
          (await leafBySearch(await page.request.get(astUrl), "GenesByGoTerm"))
            .parameters?.["go_term_evidence"]?.values,
        { timeout: 30_000 },
      )
      .toEqual(["Curated"]);

    await graphPage.changeOperator(unionId, "INTERSECT");
    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 30_000 },
    );
    await expect
      .poll(
        async () => {
          const all = await astNodes(await page.request.get(astUrl));
          return all.find((n) => n.id === unionId)?.operator;
        },
        { timeout: 30_000 },
      )
      .toBe("INTERSECT");

    await graphPage.deleteStep(taxonLeafId);
    await graphPage.expectNodeCount(3);
    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 30_000 },
    );
    await expect
      .poll(
        async () =>
          (await astNodes(await page.request.get(astUrl))).map((n) => n.id).sort(),
        { timeout: 30_000 },
      )
      .toEqual([goLeafId, textLeafId, unionId].sort());

    await page.goto(`/plasmodb/conversation/${conversationId}`);
    await graphPage.expectOnChatRoute(conversationId);
    await chatPage.send("Compare search variants for the text-kinase leaf.");
    await chatPage.expectVariantComparison();
    await chatPage.expectIdle();

    await chatPage.send("How many genes does this strategy return now?");
    await chatPage.expectAssistantMessage(/\[mock\]/i, { timeout: 90_000 });
    await chatPage.expectIdle();
  });
});
