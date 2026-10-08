/**
 * The app lives under /pathfinder: a deep link survives a reload there, and
 * the first turn on the draft route writes its own address there.
 */

import { BASE_URL, test, expect } from "../fixtures/test";
import { seedStrategy } from "../fixtures/strategy-builds";
import { openConversationId } from "../pages/navigation";

test.describe("The base path", () => {
  test("a strategy deep link survives a reload under /pathfinder", async ({
    page,
    apiClient,
    siteId,
  }) => {
    const { conversationId } = await seedStrategy(apiClient, siteId);

    await page.goto(`${siteId}/conversation/${conversationId}/strategy`);
    await expect(page.getByTestId("canvas-topbar")).toBeVisible({ timeout: 60_000 });
    await page.reload();

    await expect(page.getByTestId("canvas-topbar")).toBeVisible({ timeout: 60_000 });
    await expect(page).toHaveURL(
      `${BASE_URL}/${siteId}/conversation/${conversationId}/strategy`,
    );
  });

  test("the first turn on the draft route keeps the address under /pathfinder", async ({
    page,
    chatPage,
    siteId,
  }) => {
    await page.goto(`${siteId}/conversation`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });

    await chatPage.send("hello from the draft route");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();

    const conversationId = await openConversationId(page);
    await expect(page).toHaveURL(
      `${BASE_URL}/${siteId}/conversation/${conversationId}`,
    );
  });
});
