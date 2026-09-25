/**
 * Smoke test for the strategy overhaul UI surfaces.
 *
 * Bypasses the chat planning flow - seeds a strategy via direct API POST,
 * then exercises the new /strategy route, CanvasTopbar, rail panel, and
 * editor Sheet. Useful when the chat infrastructure is unavailable.
 */
import { test, expect } from "../fixtures/test";
import type { BrowserContext, Page } from "@playwright/test";

const SITE_ID = "plasmodb";

/** Expand the right rail's Strategy panel so the StrategyPanel content mounts. */
async function openStrategyRailPanel(page: Page): Promise<void> {
  const openBtn = page.getByRole("button", { name: /open strategy/i });
  await openBtn.click();
}

interface SeededStrategy {
  conversationId: string;
  rootStepId: string;
}

async function seedStrategyViaApi(
  ctx: BrowserContext,
  baseURL: string,
): Promise<SeededStrategy> {
  const req = ctx.request;
  const resp = await req.post(`${baseURL}/api/v1/conversations`, {
    headers: { "X-Requested-With": "XMLHttpRequest" },
    data: {
      name: "Smoke test strategy",
      siteId: SITE_ID,
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
  if (!resp.ok()) {
    const body = await resp.text();
    throw new Error(`seedStrategyViaApi: ${resp.status()} ${body}`);
  }
  const conversation = (await resp.json()) as {
    id: string;
    rootStepId: string | null;
  };
  if (conversation.rootStepId === null) {
    throw new Error("seedStrategyViaApi: rootStepId missing");
  }
  return {
    conversationId: conversation.id,
    rootStepId: conversation.rootStepId,
  };
}

test.describe("Strategy page smoke (post-overhaul)", () => {
  test.describe.configure({ mode: "serial" });

  test("rail panel renders the read-only step list with Open button", async ({
    context,
    page,
    graphPage,
  }) => {
    const baseURL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
    const { conversationId } = await seedStrategyViaApi(context, baseURL);

    await page.goto(`/${SITE_ID}/conversation/${conversationId}`);
    await openStrategyRailPanel(page);
    await graphPage.expectRailPanel();
    await expect(graphPage.railOpenButton).toBeVisible();
    await expect(graphPage.railFooter).toContainText(/step/);
    expect(await graphPage.railStepRows.count()).toBeGreaterThan(0);
  });

  test("clicking rail Open navigates to /strategy with topbar", async ({
    context,
    page,
    graphPage,
  }) => {
    const baseURL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
    const { conversationId } = await seedStrategyViaApi(context, baseURL);

    await page.goto(`/${SITE_ID}/conversation/${conversationId}`);
    await openStrategyRailPanel(page);
    await graphPage.expectRailPanel();
    await graphPage.railOpenButton.click();
    await graphPage.expectOnStrategyRoute(conversationId);
    await graphPage.expectStrategyTopbar();
    await expect(graphPage.strategyPageBackButton).toBeVisible();
    await expect(graphPage.strategyPageStepCount).toContainText(/step/);
  });

  test("clicking a step row deep-links to /strategy/step/[id] with editor open", async ({
    context,
    page,
    graphPage,
  }) => {
    const baseURL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
    const { conversationId, rootStepId } = await seedStrategyViaApi(context, baseURL);

    await page.goto(`/${SITE_ID}/conversation/${conversationId}`);
    await openStrategyRailPanel(page);
    await graphPage.expectRailPanel();
    await graphPage.railStepRow(rootStepId).click();
    await graphPage.expectOnStrategyRoute(conversationId);
    await expect(page).toHaveURL(
      new RegExp(`/conversation/${conversationId}/strategy/step/${rootStepId}`),
      { timeout: 10_000 },
    );
    await graphPage.expectEditorSheetOpen();
    await expect(graphPage.editorFooter).toBeVisible();
  });

  test("back-to-chat returns to the conversation route", async ({
    context,
    graphPage,
  }) => {
    const baseURL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
    const { conversationId } = await seedStrategyViaApi(context, baseURL);

    await graphPage.goToStrategy(SITE_ID, conversationId);
    await graphPage.expectStrategyTopbar();
    await graphPage.strategyPageBackButton.click();
    await graphPage.expectOnChatRoute(conversationId);
  });

  test("canvas controls are mounted on /strategy", async ({ context, graphPage }) => {
    const baseURL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";
    const { conversationId } = await seedStrategyViaApi(context, baseURL);

    await graphPage.goToStrategy(SITE_ID, conversationId);
    await expect(graphPage.canvasControls).toBeVisible({ timeout: 10_000 });
  });
});
