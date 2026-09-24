/**
 * A researcher rates a verified reply. A like survives a reload and pins the
 * turn's case memory; a dislike takes that case out of memory. The account
 * keeps the cases of earlier specs, so the checks follow this turn's key.
 *
 * Only the LLM is mocked: the turn runs FRAME, BUILD and VERIFY in the worker
 * against real WDK and Postgres, so its case is written by the real auto-write.
 */
import type { APIRequestContext } from "@playwright/test";

import { test, expect } from "../fixtures/test";
import { MOCK_PLAN_PROMPT, MOCK_PLAN_REPLY } from "../fixtures/mock-prompts";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

interface MemoryItem {
  key: string;
  value: { tags: string[] };
}

/** The user's case memories, key to tags. The account keeps the cases of
 * earlier specs, so a check names the key this turn wrote. */
async function cases(request: APIRequestContext): Promise<Map<string, string[]>> {
  const response = await request.get(`${BASE_URL}/api/v1/memories`, {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { cases: MemoryItem[] };
  return new Map(body.cases.map((item) => [item.key, item.value.tags]));
}

function pinnedSince(before: Map<string, string[]>, after: Map<string, string[]>) {
  return [...after]
    .filter(
      ([key, tags]) => tags.includes("pinned") && !before.get(key)?.includes("pinned"),
    )
    .map(([key]) => key);
}

test.describe("Rating an assistant message", () => {
  test("a like survives a reload and pins the case; a dislike removes it", async ({
    chatPage,
    page,
    context,
  }) => {
    await chatPage.goto();
    await chatPage.newChat();
    await chatPage.sendTurn(MOCK_PLAN_PROMPT, MOCK_PLAN_REPLY);

    const reply = chatPage.assistantReply(MOCK_PLAN_REPLY);
    await expect(reply).toHaveCount(1);
    const like = reply.getByRole("button", { name: "Good response" });
    const dislike = reply.getByRole("button", { name: "Bad response" });
    await expect(
      chatPage.userMessages.getByRole("button", { name: "Good response" }),
    ).toHaveCount(0);

    const beforeLike = await cases(context.request);
    await reply.hover();
    const liked = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" && response.url().endsWith("/rating"),
    );
    await like.click();
    expect((await liked).status()).toBe(200);
    await expect(like).toHaveAttribute("aria-pressed", "true");

    await page.reload();
    await expect(chatPage.assistantReply(MOCK_PLAN_REPLY)).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(
      chatPage
        .assistantReply(MOCK_PLAN_REPLY)
        .getByRole("button", { name: "Good response" }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect
      .poll(async () => pinnedSince(beforeLike, await cases(context.request)))
      .toHaveLength(1);
    const [likedKey] = pinnedSince(beforeLike, await cases(context.request));

    await chatPage.assistantReply(MOCK_PLAN_REPLY).hover();
    const disliked = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" && response.url().endsWith("/rating"),
    );
    await chatPage
      .assistantReply(MOCK_PLAN_REPLY)
      .getByRole("button", { name: "Bad response" })
      .click();
    expect((await disliked).status()).toBe(200);
    await expect(dislike).toHaveAttribute("aria-pressed", "true");
    await expect
      .poll(async () =>
        [...(await cases(context.request)).keys()].filter((key) => key === likedKey),
      )
      .toEqual([]);
  });
});
