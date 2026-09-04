import { type Locator, type Page } from "@playwright/test";

import { test, expect } from "../fixtures/test";
import { MOCK_PLAN_PROMPT } from "../fixtures/mock-prompts";

/**
 * Feature: the three usage surfaces agree on one live turn.
 *
 * The per-turn chip, the composer footer and the quota row read the same
 * turn. The mock provider prices every dispatch at $0, so only the token
 * counts grow; the chip and the footer are compared as the strings the
 * formatters print, because both round to the same compact form.
 */

/** A plain question: the mock echoes it and dispatches no sub-agent. */
const PLAIN_PROMPT = "hello usage totals";

interface Quota {
  totalTokens: number;
}

interface FormattedUsage {
  tokens: string;
  cost: string;
}

function normalize(text: string | null): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

/** The chip reads "<model> - <tokens>, <cost>". */
function readChip(text: string | null): FormattedUsage {
  const line = normalize(text);
  const match = /^.+ - (?<tokens>[^,]+), (?<cost>\S+)$/.exec(line);
  if (match?.groups === undefined) {
    throw new Error(`the turn chip does not read as a usage line: "${line}"`);
  }
  return { tokens: match.groups["tokens"] ?? "", cost: match.groups["cost"] ?? "" };
}

/** The footer reads "Conversation · <tokens> tokens · <cost>". */
function readFooter(text: string | null): FormattedUsage {
  const line = normalize(text);
  const match = /·\s*(?<tokens>\S+)\s+tokens\s*·\s*(?<cost>\S+)$/.exec(line);
  if (match?.groups === undefined) {
    throw new Error(`the composer footer does not read as a usage line: "${line}"`);
  }
  return { tokens: match.groups["tokens"] ?? "", cost: match.groups["cost"] ?? "" };
}

function conversationFooter(page: Page): Locator {
  return page.getByTestId("conversation-usage");
}

test.describe("Usage reconciliation", () => {
  test("the turn chip, the composer footer and the quota row read one turn the same way", async ({
    chatPage,
    apiClient,
    page,
  }) => {
    const quota = async (): Promise<Quota> => {
      const resp = await apiClient.get("/api/v1/me/quota");
      expect(resp.ok()).toBeTruthy();
      return (await resp.json()) as Quota;
    };
    const before = await quota();

    await chatPage.goto();
    await chatPage.newChat();
    await chatPage.send(MOCK_PLAN_PROMPT);
    await chatPage.expectIdle();

    // One turn carries one usage chip: the totals ride its last run alone.
    // The plan turn's reply is the one that never echoes the plain prompt, so
    // this names the same chip after the second turn lands.
    const chip = chatPage.assistantMessages
      .filter({ hasNotText: PLAIN_PROMPT })
      .getByTestId("trace-usage");
    await expect(chip).toHaveCount(1, { timeout: 60_000 });
    const chipText = normalize(await chip.textContent());
    const turnUsage = readChip(chipText);

    const footer = conversationFooter(page);
    await expect(footer).toBeVisible({ timeout: 30_000 });
    const conversationUsage = readFooter(await footer.textContent());

    // A one-turn conversation: the turn total IS the conversation total.
    expect(turnUsage.tokens).toBe(conversationUsage.tokens);
    expect(turnUsage.cost).toBe(conversationUsage.cost);

    // The mock prices every dispatch at $0, so only the tokens grow.
    await expect
      .poll(async () => (await quota()).totalTokens, { timeout: 30_000 })
      .toBeGreaterThan(before.totalTokens);

    // A second turn grows the conversation total and leaves the first
    // turn's own chip untouched.
    await chatPage.send(PLAIN_PROMPT);
    await chatPage.expectAssistantMessage(/\[mock\].*hello usage totals/);
    await chatPage.expectIdle();

    await expect
      .poll(async () => readFooter(await footer.textContent()).tokens, {
        timeout: 60_000,
      })
      .not.toBe(conversationUsage.tokens);
    await expect(chip).toHaveCount(1);
    expect(normalize(await chip.textContent())).toBe(chipText);
  });
});
