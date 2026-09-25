import { test, expect } from "../fixtures/test";
import type { Page } from "@playwright/test";
import { astNodes, combineOperators, leafIdBySearch } from "../fixtures/ast";
import type { ChatPage } from "../pages/chat.page";
import type { SitePickerComponent } from "../pages/site-picker.page";

/** Build the two-leaf kinase strategy and return its conversation id. */
async function buildTwoLeafStrategy(
  chatPage: ChatPage,
  sitePicker: SitePickerComponent,
): Promise<string> {
  await chatPage.goto();
  await sitePicker.selectSite("plasmodb");
  await chatPage.newChat("plasmodb");
  await chatPage.send(
    "Build a strategy for P. falciparum 3D7 kinases using InterPro PF00069 and GO terms.",
  );
  await chatPage.expectVerificationFeedback();
  const id = chatPage.lastStrategyId;
  expect(id).toBeTruthy();
  return id as string;
}

test.describe("Intersect with a copy + rename step from UI", () => {
  test("intersecting a leaf with a copy via the node kebab adds steps to the AST", async ({
    page,
    chatPage,
    graphPage,
    sitePicker,
    apiClient,
  }) => {
    const conversationId = await buildTwoLeafStrategy(chatPage, sitePicker);
    const astUrl = `/api/v1/conversations/${conversationId}/ast`;

    expect((await astNodes(await apiClient.get(astUrl))).length).toBe(3);
    const leafId = await leafIdBySearch(await apiClient.get(astUrl), "GenesByText");

    await graphPage.goToStrategy("plasmodb", conversationId);
    await graphPage.expectStrategyTopbar();
    await graphPage.expectNodeVisible(leafId);

    await intersectWithACopy(page, leafId);

    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 45_000 },
    );

    // The copy arrives with its own combine, so the tree grows by two nodes.
    await expect
      .poll(async () => (await astNodes(await apiClient.get(astUrl))).length, {
        timeout: 30_000,
      })
      .toBe(5);

    expect(await combineOperators(await apiClient.get(astUrl))).toEqual([
      "INTERSECT",
      "UNION",
    ]);
    const ids = (await astNodes(await apiClient.get(astUrl))).map((n) => n.id);
    expect(ids).toContain(leafId);
  });

  test("renaming a leaf via the editor persists displayName to the AST", async ({
    chatPage,
    graphPage,
    sitePicker,
    apiClient,
  }) => {
    const conversationId = await buildTwoLeafStrategy(chatPage, sitePicker);
    const astUrl = `/api/v1/conversations/${conversationId}/ast`;
    const leafId = await leafIdBySearch(await apiClient.get(astUrl), "GenesByText");

    await graphPage.goToStrategy("plasmodb", conversationId);
    await graphPage.expectStrategyTopbar();
    await graphPage.expectNodeVisible(leafId);

    await graphPage.clickNode(leafId);
    await expect(graphPage.editorSheet).toBeVisible({ timeout: 20_000 });
    const nameInput = graphPage.editorStepNameInput;
    await nameInput.fill("Renamed kinase leaf");
    await nameInput.press("Enter");

    const save = graphPage.editorSheet.getByTestId("step-editor-save");
    await expect(save).toBeVisible({ timeout: 15_000 });
    await save.click();

    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 30_000 },
    );

    await expect
      .poll(
        async () => {
          const all = await astNodes(await apiClient.get(astUrl));
          return all.find((n) => n.id === leafId)?.displayName;
        },
        { timeout: 30_000 },
      )
      .toBe("Renamed kinase leaf");
  });
});

async function intersectWithACopy(page: Page, stepId: string): Promise<void> {
  await page.getByTestId(`rf-node-${stepId}`).hover();
  await page.getByTestId(`rf-more-${stepId}`).click();
  await page.getByRole("menuitem", { name: "Intersect with a copy" }).click();
}
