import { test, expect } from "../fixtures/test";
import type { APIRequestContext } from "@playwright/test";
import { signInAsWdkAccount } from "../fixtures/wdk-account";
import { astNodes, leafIdBySearch } from "../fixtures/ast";
import type { ChatPage } from "../pages/chat.page";
import type { SitePickerComponent } from "../pages/site-picker.page";

/** The leaf of the two-leaf kinase spec that a saved strategy is combined with. */
const TARGET_LEAF_SEARCH = "GenesByText";

/**
 * Build the two-leaf kinase strategy. Its verification reports a zero-result
 * leaf, and the steps are pushed either way, so the strategy is insertable.
 */
async function buildInterpro(
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

async function buildPlasmo(
  chatPage: ChatPage,
  sitePicker: SitePickerComponent,
): Promise<string> {
  await chatPage.goto();
  await sitePicker.selectSite("plasmodb");
  await chatPage.newChat("plasmodb");
  await chatPage.send("create delegation");
  await chatPage.expectVerificationSuccess();
  await chatPage.expectIdle();
  const id = chatPage.lastStrategyId;
  expect(id).toBeTruthy();
  return id as string;
}

/** The id of the leaf a saved strategy is inserted next to. */
async function targetLeafId(
  api: APIRequestContext,
  conversationId: string,
): Promise<string> {
  return leafIdBySearch(
    await api.get(`/api/v1/conversations/${conversationId}/ast`),
    TARGET_LEAF_SEARCH,
  );
}

async function wdkStrategyIdOf(
  apiClient: APIRequestContext,
  conversationId: string,
): Promise<number | null> {
  const resp = await apiClient.get(`/api/v1/conversations/${conversationId}`);
  expect(resp.ok()).toBeTruthy();
  return ((await resp.json()) as { wdkStrategyId: number | null }).wdkStrategyId;
}

test.describe("Insert saved sub-strategy", () => {
  test("returns a clean 404 / 422 on unloadable saved id and malformed body", async ({
    chatPage,
    sitePicker,
    apiClient,
  }) => {
    const targetConvId = await buildInterpro(chatPage, sitePicker);
    // A real step id, so the 404 can only come from the saved strategy id.
    const stepId = await targetLeafId(apiClient, targetConvId);

    const notFound = await apiClient.post(
      `/api/v1/conversations/${targetConvId}/insert-saved`,
      {
        params: { siteId: "plasmodb" },
        data: {
          targetStepId: stepId,
          savedWdkStrategyId: 999_999_999,
          operator: "UNION",
        },
      },
    );
    expect(notFound.status()).toBe(404);
    expect(notFound.headers()["content-type"]).toContain("application/problem+json");
    const body = (await notFound.json()) as { code: string; status: number };
    expect(body.code).toBe("STRATEGY_NOT_FOUND");
    expect(body.status).toBe(404);

    const malformed = await apiClient.post(
      `/api/v1/conversations/${targetConvId}/insert-saved`,
      {
        params: { siteId: "plasmodb" },
        data: { savedWdkStrategyId: 123, operator: "UNION" },
      },
    );
    expect(malformed.status()).toBe(422);
  });

  test("inserts a saved WDK strategy as an expanded combine input (real account)", async ({
    page,
    chatPage,
    sitePicker,
  }) => {
    test.setTimeout(180_000);

    const ctx = page.context().request;
    const csrf = { "X-Requested-With": "XMLHttpRequest" };
    await signInAsWdkAccount(ctx, "plasmodb");
    await page.reload();

    const created: string[] = [];
    try {
      const savedConvId = await buildPlasmo(chatPage, sitePicker);
      created.push(savedConvId);
      await expect
        .poll(() => wdkStrategyIdOf(ctx, savedConvId), { timeout: 60_000 })
        .toBeTruthy();
      const savedWdkStrategyId = await wdkStrategyIdOf(ctx, savedConvId);
      const marked = await ctx.patch(`/api/v1/conversations/${savedConvId}`, {
        data: { isSaved: true },
        headers: csrf,
      });
      expect(marked.ok()).toBeTruthy();

      const targetConvId = await buildInterpro(chatPage, sitePicker);
      created.push(targetConvId);
      await expect
        .poll(() => wdkStrategyIdOf(ctx, targetConvId), { timeout: 60_000 })
        .toBeTruthy();
      const before = (
        await astNodes(await ctx.get(`/api/v1/conversations/${targetConvId}/ast`))
      ).length;
      const stepId = await targetLeafId(ctx, targetConvId);

      const inserted = await ctx.post(
        `/api/v1/conversations/${targetConvId}/insert-saved`,
        {
          params: { siteId: "plasmodb" },
          data: {
            targetStepId: stepId,
            savedWdkStrategyId: savedWdkStrategyId as number,
            operator: "UNION",
          },
          headers: csrf,
        },
      );
      expect(
        inserted.ok(),
        `insert ${inserted.status()}: ${await inserted.text()}`,
      ).toBeTruthy();
      const result = (await inserted.json()) as {
        insertedSavedWdkStrategyId: number;
        combineStepId: string;
        wdkStrategyId: number;
      };
      expect(result.insertedSavedWdkStrategyId).toBe(savedWdkStrategyId);
      expect(result.combineStepId).toBeTruthy();
      expect(typeof result.wdkStrategyId).toBe("number");

      const after = await astNodes(
        await ctx.get(`/api/v1/conversations/${targetConvId}/ast`),
      );
      expect(after.length).toBeGreaterThan(before);
      const expandedRefs = after
        .filter((n) => n.searchName === "__combine__")
        .map((n) => n.expandedStrategyId)
        .filter((v): v is number => v != null);
      expect(expandedRefs).toContain(savedWdkStrategyId);
    } finally {
      for (const id of created) {
        await ctx
          .delete(`/api/v1/conversations/${id}`, {
            params: { deleteFromWdk: "true" },
            headers: csrf,
          })
          .catch(() => undefined);
      }
    }
  });
});
