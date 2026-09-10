import { type Locator, type Page } from "@playwright/test";

import { formatUsage } from "@/features/conversation/usageFormat";

import { test, expect } from "../fixtures/test";
import { fetchLastTurnUsage } from "../fixtures/api-client";
import { MOCK_PLAN_PROMPT, MOCK_PLAN_REPLY } from "../fixtures/mock-prompts";

/**
 * Feature: the three usage surfaces agree on one live turn.
 *
 * The per-turn chip, the composer footer and the quota row read the same
 * turn. The chip and the footer are compared as the strings the formatters
 * print, because both round to the same compact form.
 */

/** A plain question: the mock echoes it and dispatches no sub-agent. */
const PLAIN_PROMPT = "hello usage totals";
const ECHO_REPLY = /\[mock\].*hello usage totals/;

interface Quota {
  totalTokens: number;
}

interface FormattedUsage {
  tokens: string;
  cost: string;
}

interface ChipUsage extends FormattedUsage {
  model: string;
}

function normalize(text: string | null): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

/** The chip reads "<model> - <tokens>, <cost>". */
function readChip(text: string | null): ChipUsage {
  const line = normalize(text);
  const match = /^(?<model>.+) - (?<tokens>[^,]+), (?<cost>\S+)$/.exec(line);
  if (match?.groups === undefined) {
    throw new Error(`the turn chip does not read as a usage line: "${line}"`);
  }
  return {
    model: match.groups["model"] ?? "",
    tokens: match.groups["tokens"] ?? "",
    cost: match.groups["cost"] ?? "",
  };
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
    // The echo turn is small, so a plan turn after it moves every reading.
    await chatPage.send(PLAIN_PROMPT);
    await chatPage.awaitTurn(ECHO_REPLY);

    // One turn carries one usage chip: the totals ride its last run alone.
    // The echo turn's reply is the one that quotes the plain prompt, so this
    // names the same chip after the second turn lands.
    const chip = chatPage.assistantMessages
      .filter({ hasText: PLAIN_PROMPT })
      .getByTestId("trace-usage");
    await expect(chip).toHaveCount(1, { timeout: 60_000 });
    const chipText = normalize(await chip.textContent());
    const turnUsage = readChip(chipText);

    // The third reading: what the API counted for the turn.
    const echoTurn = await fetchLastTurnUsage(apiClient, chatPage.lastStrategyId);
    expect(chipText).toBe(
      `${turnUsage.model} - ${formatUsage(echoTurn.totalTokens, echoTurn.costUsd)}`,
    );

    const footer = conversationFooter(page);
    await expect(footer).toBeVisible({ timeout: 30_000 });
    const conversationUsage = readFooter(await footer.textContent());

    // A one-turn conversation: the turn total IS the conversation total.
    expect(turnUsage.tokens).toBe(conversationUsage.tokens);
    expect(turnUsage.cost).toBe(conversationUsage.cost);

    // The quota row counts the turn the thread just read.
    await expect
      .poll(async () => (await quota()).totalTokens, { timeout: 30_000 })
      .toBeGreaterThan(before.totalTokens);

    // A second turn grows the conversation total and leaves the first
    // turn's own chip untouched.
    await chatPage.send(MOCK_PLAN_PROMPT);
    await chatPage.awaitTurn(MOCK_PLAN_REPLY);

    await expect
      .poll(async () => readFooter(await footer.textContent()).tokens, {
        timeout: 60_000,
      })
      .not.toBe(conversationUsage.tokens);
    await expect(chip).toHaveCount(1);
    expect(normalize(await chip.textContent())).toBe(chipText);

    // The plan turn dispatches sub-agents, and one of them runs more than one
    // pass. Its chip still reads the whole turn, as the API counted it.
    const planTurn = await fetchLastTurnUsage(apiClient, chatPage.lastStrategyId);
    const planChip = chatPage.assistantMessages
      .filter({ hasText: MOCK_PLAN_REPLY })
      .getByTestId("trace-usage");
    const planText = normalize(await planChip.textContent());
    expect(planText).toBe(
      `${readChip(planText).model} - ${formatUsage(planTurn.totalTokens, planTurn.costUsd)}`,
    );
  });
});
