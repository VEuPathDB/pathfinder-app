/**
 * The strategy surfaces on a strategy made through the api, with no turn: the
 * rail's step list, the canvas route and its topbar, the step editor and the
 * keys that move between them.
 */

import type { ConversationResponse } from "@pathfinder/shared";

import { test, expect } from "../fixtures/test";
import type { ApiClient } from "../fixtures/api-client";

interface SeededStrategy {
  conversationId: string;
  rootStepId: string;
}

/** A one-step strategy stored through the api on `siteId`. */
async function seedStrategy(api: ApiClient, siteId: string): Promise<SeededStrategy> {
  const resp = await api.post("/api/v1/conversations", {
    data: {
      name: "Smoke test strategy",
      siteId,
      strategyAst: {
        recordType: "transcript",
        root: {
          searchName: "GenesByText",
          parameters: {
            text_expression: { type: "string", value: "kinase" },
            text_fields: {
              type: "string",
              value: '["primary_key","gene_product"]',
            },
            document_type: { type: "string", value: "gene" },
            max_pvalue: { type: "number", value: 0.5 },
          },
          displayName: "All kinase transcripts",
        },
      },
    },
  });
  expect(resp.status(), `seed ${await resp.text()}`).toBe(201);
  const conversation = (await resp.json()) as ConversationResponse;
  const rootStepId = conversation.rootStepId ?? "";
  expect(rootStepId).not.toBe("");
  return { conversationId: conversation.id, rootStepId };
}

test.describe("Strategy page smoke", () => {
  test("the rail lists the step and opens the canvas, and Esc returns", async ({
    page,
    graphPage,
    apiClient,
    siteId,
  }) => {
    const { conversationId } = await seedStrategy(apiClient, siteId);

    await page.goto(`/${siteId}/conversation/${conversationId}`);
    await graphPage.openRailStrategyPanel();
    await expect(graphPage.railOpenButton).toBeVisible();
    await expect(graphPage.railFooter).toHaveText("1 step");
    await expect(graphPage.railStepRows).toHaveCount(1);

    await graphPage.railOpenButton.click();
    await graphPage.expectOnStrategyRoute(conversationId);
    await graphPage.expectStrategyTopbar();
    await expect(graphPage.strategyPageNameInput).toBeVisible();
    await expect(graphPage.strategyPageStepCount).toHaveText("1 step");
    await expect(graphPage.strategyPageSyncState).toBeVisible();
    await expect(graphPage.strategyPageBackButton).toBeVisible();
    await expect(graphPage.canvasControls).toBeVisible({ timeout: 10_000 });
    await expect(graphPage.selectionActionBar).toBeHidden();

    await page.keyboard.press("Escape");
    await graphPage.expectOnChatRoute(conversationId);
  });

  test("a rail row deep-links to its step, and a reload keeps the editor open", async ({
    page,
    graphPage,
    apiClient,
    siteId,
  }) => {
    const { conversationId, rootStepId } = await seedStrategy(apiClient, siteId);

    await page.goto(`/${siteId}/conversation/${conversationId}`);
    await graphPage.openRailStrategyPanel();
    await graphPage.railStepRow(rootStepId).click();
    await expect(page).toHaveURL(
      new RegExp(`/conversation/${conversationId}/strategy/step/${rootStepId}`),
      { timeout: 10_000 },
    );
    await graphPage.expectEditorSheetOpen();
    await expect(graphPage.editorFooter).toBeVisible();
    await expect(graphPage.editorStepNameInput).toBeVisible();

    await page.reload();
    await graphPage.expectOnStrategyRoute(conversationId);
    await graphPage.expectEditorSheetOpen();
  });

  test("Esc closes the editor, and a second Esc returns to the conversation", async ({
    page,
    graphPage,
    apiClient,
    siteId,
  }) => {
    const { conversationId, rootStepId } = await seedStrategy(apiClient, siteId);

    await graphPage.goToStrategy(siteId, conversationId);
    await graphPage.clickNode(rootStepId);
    await graphPage.expectEditorSheetOpen();

    await page.keyboard.press("Escape");
    await graphPage.expectEditorSheetClosed();
    await graphPage.expectOnStrategyRoute(conversationId);

    await page.keyboard.press("Escape");
    await graphPage.expectOnChatRoute(conversationId);
    await graphPage.openRailStrategyPanel();
    await expect(graphPage.railStepRows).toHaveCount(1);
  });

  test("Back to conversation returns to the conversation route", async ({
    graphPage,
    apiClient,
    siteId,
  }) => {
    const { conversationId } = await seedStrategy(apiClient, siteId);

    await graphPage.goToStrategy(siteId, conversationId);
    await graphPage.expectStrategyTopbar();
    await graphPage.strategyPageBackButton.click();
    await graphPage.expectOnChatRoute(conversationId);
  });

  test("the r key lays the graph out again and keeps its node", async ({
    page,
    graphPage,
    apiClient,
    siteId,
  }) => {
    const { conversationId, rootStepId } = await seedStrategy(apiClient, siteId);

    await graphPage.goToStrategy(siteId, conversationId);
    await graphPage.expectStrategyTopbar();
    await graphPage.expectNodeCount(1);

    await page.mouse.click(400, 400);
    await page.keyboard.press("r");
    await graphPage.expectNodeCount(1);
    await graphPage.expectNodeVisible(rootStepId);
  });

  test("a strategy that validates shows no validation alert", async ({
    graphPage,
    apiClient,
    siteId,
  }) => {
    const { conversationId } = await seedStrategy(apiClient, siteId);

    await graphPage.goToStrategy(siteId, conversationId);
    await graphPage.expectStrategyTopbar();
    await expect(graphPage.validationAlert).toBeHidden();
  });

  test("the editor's More actions menu is reachable past the close button", async ({
    page,
    graphPage,
    apiClient,
    siteId,
  }) => {
    const { conversationId, rootStepId } = await seedStrategy(apiClient, siteId);

    await graphPage.goToStrategy(siteId, conversationId);
    await graphPage.clickNode(rootStepId);
    await graphPage.expectEditorSheetOpen();
    await graphPage.editorSheet
      .getByRole("button", { name: "More actions" })
      .click({ timeout: 10_000 });
    await expect(page.getByRole("menuitem", { name: "Delete step" })).toBeVisible({
      timeout: 5_000,
    });
  });
});
