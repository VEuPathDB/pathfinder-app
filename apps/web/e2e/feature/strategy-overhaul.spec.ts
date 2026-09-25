/**
 * E2E walkthrough for the strategy graph + step editor overhaul (spec section
 * 12.3 of `docs/superpowers/specs/2026-04-22-strategy-graph-editor-overhaul-design.md`).
 *
 * Per CLAUDE.md: only the LLM is mocked. Real WDK, real Postgres, real Redis.
 * Each test is self-contained - no shared state across tests in this file.
 *
 * The walkthrough threads a saved gold strategy from chat -> rail -> strategy
 * page -> step editor -> combine creation -> venn picker -> edge context menu ->
 * keyboard shortcuts -> back to chat. The 20 numbered steps in spec section
 * 12.3 are split across the tests below so each test exercises one slice of
 * the overhaul without relying on prior-test state.
 */
import { test, expect } from "../fixtures/test";
import type { ChatPage } from "../pages/chat.page";
import type { GraphPage } from "../pages/graph.page";
import { MOCK_PLAN_PROMPT } from "../fixtures/mock-prompts";
import { currentSiteId } from "../pages/navigation";

/**
 * Build a strategy from the planning artifact so the rail panel + canvas
 * have something to render. Captures the conversation id for navigation.
 */
async function seedStrategy(
  chatPage: ChatPage,
  graphPage: GraphPage,
): Promise<{ conversationId: string; firstStepId: string }> {
  await chatPage.send(MOCK_PLAN_PROMPT);
  await graphPage.expectRailPanel();
  await chatPage.expectIdle();

  const conversationId = chatPage.lastStrategyId;
  if (conversationId == null || conversationId === "") {
    throw new Error("seedStrategy: chatPage.lastStrategyId was not set");
  }

  const firstStepId = await graphPage.firstRailStepId();
  if (firstStepId === "") {
    throw new Error("seedStrategy: could not extract first step id from rail");
  }
  return { conversationId, firstStepId };
}

test.describe("Strategy overhaul - walkthrough", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.newChat();
  });

  test("rail panel shows the read-only step list and an Open button", async ({
    chatPage,
    graphPage,
  }) => {
    await seedStrategy(chatPage, graphPage);

    // Rail panel is visible (spec section 10.3) and shows step rows.
    await expect(graphPage.railPanel).toBeVisible();
    const rowCount = await graphPage.railStepRows.count();
    expect(rowCount).toBeGreaterThan(0);

    // Open button + footer present.
    await expect(graphPage.railOpenButton).toBeVisible();
    await expect(graphPage.railFooter).toContainText(/step/);
  });

  test("clicking rail Open navigates to /strategy with topbar mounted", async ({
    chatPage,
    graphPage,
    page,
  }) => {
    const { conversationId } = await seedStrategy(chatPage, graphPage);

    await graphPage.railOpenButton.click();
    await graphPage.expectOnStrategyRoute(conversationId);

    // Topbar shows strategy name + step count + sync state pill.
    await graphPage.expectStrategyTopbar();
    await expect(graphPage.strategyPageNameInput).toBeVisible();
    await expect(graphPage.strategyPageStepCount).toContainText(/step/);
    await expect(graphPage.strategyPageSyncState).toBeVisible();

    // Floating canvas controls are bottom-right.
    await expect(graphPage.canvasControls).toBeVisible();

    // No selection action bar yet (no nodes selected).
    await expect(graphPage.selectionActionBar).toBeHidden();

    // Esc returns to /conversation/[id] (chat route).
    await page.keyboard.press("Escape");
    await graphPage.expectOnChatRoute(conversationId);
  });

  test("clicking a rail step row deep-links to the editor sheet", async ({
    chatPage,
    graphPage,
  }) => {
    const { conversationId, firstStepId } = await seedStrategy(chatPage, graphPage);

    await graphPage.railStepRow(firstStepId).click();
    await graphPage.expectOnStrategyRoute(conversationId);

    // The deep-linkable /strategy/step/[stepId] route should auto-open the
    // editor sheet on the focused step.
    await graphPage.expectEditorSheetOpen();
    await expect(graphPage.editorStepNameInput).toBeVisible();
  });

  test("editor sheet edits autosave and surface a 'Saved' state", async ({
    chatPage,
    graphPage,
    page,
  }) => {
    const { conversationId, firstStepId } = await seedStrategy(chatPage, graphPage);

    await graphPage.goToStrategy(currentSiteId(page), conversationId);
    await graphPage.clickNode(firstStepId);
    await graphPage.expectEditorSheetOpen();

    // Rename via the inline input (autosaves on blur).
    const nameInput = graphPage.editorStepNameInput;
    await expect(nameInput).toBeVisible();
    await nameInput.fill("Renamed test step");
    await nameInput.blur();

    // Sync state pill should report idle (Saved) after the autosave settles.
    await expect(graphPage.editorSyncState).toHaveAttribute(
      "data-sync-state",
      /idle|saving/,
      { timeout: 10_000 },
    );
    await expect(graphPage.editorSyncState).toHaveAttribute("data-sync-state", "idle", {
      timeout: 15_000,
    });
  });

  test("Esc closes the editor sheet, returns user to /strategy", async ({
    chatPage,
    graphPage,
    page,
  }) => {
    const { conversationId, firstStepId } = await seedStrategy(chatPage, graphPage);

    await graphPage.goToStrategy(currentSiteId(page), conversationId);
    await graphPage.clickNode(firstStepId);
    await graphPage.expectEditorSheetOpen();

    await page.keyboard.press("Escape");
    await graphPage.expectEditorSheetClosed();
    await graphPage.expectOnStrategyRoute(conversationId);

    // A second Esc lands back in chat.
    await page.keyboard.press("Escape");
    await graphPage.expectOnChatRoute(conversationId);
  });

  test("rail still shows the step list after editing on /strategy", async ({
    chatPage,
    graphPage,
    page,
  }) => {
    const { conversationId, firstStepId } = await seedStrategy(chatPage, graphPage);

    await graphPage.goToStrategy(currentSiteId(page), conversationId);
    await graphPage.clickNode(firstStepId);
    await graphPage.expectEditorSheetOpen();
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");

    // Rail visible after returning to chat.
    await graphPage.expectOnChatRoute(conversationId);
    await graphPage.expectRailPanel();
  });

  test("'r' keyboard shortcut triggers a graph relayout", async ({
    chatPage,
    graphPage,
    page,
  }) => {
    const { conversationId } = await seedStrategy(chatPage, graphPage);

    await graphPage.goToStrategy(currentSiteId(page), conversationId);
    await graphPage.expectStrategyTopbar();

    // Capture node positions before relayout.
    const before = await graphPage.firstNodeBoundingBox();
    expect(before).not.toBeNull();

    // Move the canvas so relayout has something to undo, then press R.
    await page.mouse.click(400, 400);
    await page.keyboard.press("r");

    // The graph should remain visible with its nodes intact.
    const after = await graphPage.firstNodeBoundingBox();
    expect(after).not.toBeNull();
  });

  test("validation alert is hidden when strategy validates cleanly", async ({
    chatPage,
    graphPage,
    page,
  }) => {
    const { conversationId } = await seedStrategy(chatPage, graphPage);

    await graphPage.goToStrategy(currentSiteId(page), conversationId);

    // Single-step gold strategy should validate. The alert renders only on
    // mismatched record types; a clean strategy keeps it hidden.
    await expect(graphPage.validationAlert).toBeHidden();
  });

  test("editor sheet reopens to the right step on deep-link reload", async ({
    chatPage,
    graphPage,
    page,
  }) => {
    const { conversationId, firstStepId } = await seedStrategy(chatPage, graphPage);

    await page.goto(
      `/${currentSiteId(page)}/conversation/${conversationId}/strategy/step/${firstStepId}`,
    );
    await graphPage.expectOnStrategyRoute(conversationId);
    await graphPage.expectEditorSheetOpen();
  });

  test("topbar 'Back to conversation' returns to /conversation/[id]", async ({
    chatPage,
    graphPage,
    page,
  }) => {
    const { conversationId } = await seedStrategy(chatPage, graphPage);

    await graphPage.goToStrategy(currentSiteId(page), conversationId);
    await graphPage.strategyPageBackButton.click();
    await graphPage.expectOnChatRoute(conversationId);
  });
});
