/**
 * One strategy's life on the canvas: a five-node build over three searches, a
 * text edit, a multi-pick edit, an operator flip and a deletion, then a variant
 * comparison and a count question in the conversation.
 */

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import { type AstNode, COMBINE_SEARCH_NAME } from "../fixtures/ast";
import { GO_TERM, layoutOf } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readNodes, siteOrganism, storedNodes } from "../fixtures/site-reads";
import { signInAsWdkAccount } from "../fixtures/wdk-account";
import {
  buildOn,
  combineWith,
  expectCanvasSaved,
  expectCountAnswered,
  nodeById,
  noteSiteRefusedSave,
  nodeBySearch,
  openCanvas,
  paramText,
} from "../fixtures/strategy-builds";

const TEXT_SEARCH = "GenesByText";
/** The words the researcher types into the text search. */
const EDITED_TEXT = "phosphatase";

/** A multi-pick parameter's stored values. */
function pickedValues(node: AstNode, name: string): string[] {
  return (node.parameters?.[name]?.values ?? []).map(String);
}

test.describe("Comprehensive strategy lifecycle", { tag: "@turn" }, () => {
  test.use({ viewport: { width: 1680, height: 900 } });
  test.describe.configure({ timeout: 900_000 });

  test("build five nodes -> edit a text and a multi-pick parameter -> flip -> delete -> variants -> count", async ({
    page,
    chatPage,
    graphPage,
    siteId,
  }) => {
    const api = page.context().request;
    await signInAsWdkAccount(api, siteId);

    const id = await buildOn(
      chatPage,
      siteId,
      prompt(
        "combined",
        `Build a ${siteOrganism(siteId)} strategy that combines a product-text search, a GO term search and the organism's genes.`,
      ),
    );
    await expect
      .poll(async () => (await storedNodes(api, id)).length, { timeout: 60_000 })
      .toBe(5);
    const built = await readNodes(api, id);
    await expectBuild(page, api, id, siteId, layoutOf(built));
    expect(layoutOf(built).operators).toEqual(["INTERSECT", "UNION"]);
    const union = combineWith(built, "UNION");
    const intersect = combineWith(built, "INTERSECT");
    const textLeaf = nodeBySearch(built, TEXT_SEARCH);
    const goLeaf = nodeBySearch(built, GO_TERM);
    expect([union.primaryInput?.id, union.secondaryInput?.id].sort()).toEqual(
      [textLeaf.id, goLeaf.id].sort(),
    );
    const inputs = [intersect.primaryInput?.id, intersect.secondaryInput?.id];
    expect(inputs).toContain(union.id);
    const lastLeafId = inputs.find((input) => input !== union.id) ?? "";
    expect(nodeById(built, lastLeafId).searchName).not.toBe(COMBINE_SEARCH_NAME);

    await openCanvas(graphPage, siteId, id);
    await graphPage.expectNodeCount(5);

    const storedText = paramText(textLeaf, "text_expression");
    expect(storedText).not.toBe(EDITED_TEXT);
    await graphPage.clickNode(textLeaf.id ?? "");
    await graphPage.expectEditorSheetOpen();
    const textInput = graphPage.editorSheet.locator('input[name="text_expression"]');
    await expect(textInput).toHaveValue(storedText);
    await textInput.fill(EDITED_TEXT);
    if ((await graphPage.saveEditorOrSiteRefusal()) === "site-refused") {
      noteSiteRefusedSave(TEXT_SEARCH);
      return;
    }
    await expect
      .poll(
        async () =>
          paramText(
            nodeBySearch(await readNodes(api, id), TEXT_SEARCH),
            "text_expression",
          ),
        { timeout: 30_000 },
      )
      .toBe(EDITED_TEXT);

    const evidence = pickedValues(goLeaf, "go_term_evidence");
    expect(evidence.length).toBeGreaterThan(1);
    const dropped = evidence.at(-1) ?? "";
    await graphPage.clickNode(goLeaf.id ?? "");
    await graphPage.expectEditorSheetOpen();
    await graphPage.expandEditorAdvanced();
    await graphPage.toggleEditorCheckbox(dropped);
    if ((await graphPage.saveEditorOrSiteRefusal()) === "site-refused") {
      noteSiteRefusedSave(GO_TERM);
      return;
    }
    await expect
      .poll(
        async () =>
          pickedValues(
            nodeBySearch(await readNodes(api, id), GO_TERM),
            "go_term_evidence",
          ),
        { timeout: 30_000 },
      )
      .toEqual(evidence.filter((value) => value !== dropped));

    await graphPage.changeOperator(union.id ?? "", "INTERSECT");
    await expectCanvasSaved(graphPage);
    await expect
      .poll(async () => nodeById(await readNodes(api, id), union.id ?? "").operator, {
        timeout: 30_000,
      })
      .toBe("INTERSECT");

    await graphPage.deleteStep(lastLeafId);
    await graphPage.expectNodeCount(3);
    await expectCanvasSaved(graphPage);
    await expect
      .poll(async () => (await readNodes(api, id)).map((node) => node.id).sort(), {
        timeout: 30_000,
      })
      .toEqual([goLeaf.id, textLeaf.id, union.id].sort());

    await page.goto(`/${siteId}/conversation/${id}`);
    await graphPage.expectOnChatRoute(id);
    await chatPage.sendAndSettle(
      prompt("variants", "Compare search variants for the text search step."),
    );
    await chatPage.expectVariantComparison();

    await expectCountAnswered(chatPage, api, id, siteId);
  });
});
