import { test, expect } from "../fixtures/test";
import { entrySiteId } from "../fixtures/entry-site";
import { sseDone, sseFrame, uiMessageStreamHeaders } from "../fixtures/sse";
import type { BrowserContext } from "@playwright/test";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

interface OpenStrategyResponse {
  conversationId?: string;
  strategyId?: string;
  id?: string;
}

async function openStrategy(context: BrowserContext, siteId: string): Promise<string> {
  const resp = await context.request.post(`${BASE_URL}/api/v1/conversations/open`, {
    data: { siteId },
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!resp.ok()) throw new Error(`openStrategy failed: ${resp.status()}`);
  const body = (await resp.json()) as OpenStrategyResponse;
  const id = body.conversationId ?? body.strategyId ?? body.id;
  if (id === undefined || id === "") throw new Error("openStrategy returned no id");
  return id;
}

test.describe("Recalled memories", () => {
  test("renders the recalled-memory card from data-memory-retrieved", async ({
    page,
    context,
  }) => {
    const siteId = await entrySiteId(context, BASE_URL);
    const strategyId = await openStrategy(context, siteId);

    const chatStream = [
      sseFrame({
        type: "start",
        messageId: "44444444-4444-4444-4444-444444444444",
        messageMetadata: {
          phase: "scoping",
          model: "mock:deterministic",
          traceId: "mock-trace",
          createdAt: new Date().toISOString(),
        },
      }),
      sseFrame({
        type: "data-memory-retrieved",
        data: {
          memories: [
            {
              key: "k1",
              kind: "strategy",
              name: "P. falciparum kinome sweep",
              summary: "Prior malaria kinase strategy",
              score: 0.83,
            },
            {
              key: "k2",
              kind: "gene_set",
              name: "PF3D7 kinases",
              summary: "142 kinase genes",
              score: 0.61,
            },
          ],
        },
      }),
      sseFrame({ type: "text-start", id: "t1" }),
      sseFrame({ type: "text-delta", id: "t1", delta: "Using your prior work." }),
      sseFrame({ type: "text-end", id: "t1" }),
      sseFrame({ type: "finish", finishReason: "stop" }),
      sseDone(),
    ].join("");

    await page.route("**/api/v1/chat", async (route) => {
      await route.fulfill({
        status: 200,
        headers: uiMessageStreamHeaders(),
        body: chatStream,
      });
    });

    await page.goto(`/${siteId}/conversation/${strategyId}`);
    const composer = page.getByTestId("message-input");
    await expect(composer).toBeVisible({ timeout: 30_000 });
    await composer.click();
    await composer.pressSequentially("continue my malaria work", { delay: 15 });
    await expect(page.getByRole("button", { name: /Send/i })).toBeEnabled({
      timeout: 15_000,
    });
    await composer.press("Enter");

    const card = page.getByTestId("data-memory-retrieved");
    await expect(card).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("figure-caption")).toContainText("2 memories");
    await expect(card).toContainText("strategy");
    await expect(card).toContainText("P. falciparum kinome sweep");
    await expect(card).toContainText("gene_set");
    await expect(card).toContainText("PF3D7 kinases");
  });
});
