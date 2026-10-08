/**
 * Helpers the strategy feature specs share: a build on a fresh conversation,
 * a one-step strategy stored through the api, the stored step a search runs
 * and its parameters, the canvas once it has settled, the steps a delete card
 * says go, and the count question the recap arc answers.
 */

import type { ConversationResponse } from "@pathfinder/shared";
import { expect, test, type Locator } from "@playwright/test";

import { prompt } from "./arcs";
import type { ApiClient } from "./api-client";
import { type AstNode, COMBINE_SEARCH_NAME } from "./ast";
import { siteCounts } from "./site-reads";
import type { ChatPage } from "../pages/chat.page";
import type { GraphPage } from "../pages/graph.page";

export const COUNT_QUESTION = "How many genes does this strategy return?";

interface SeededStrategy {
  conversationId: string;
  rootStepId: string;
}

/** A one-step strategy stored through the api on `siteId`. */
export async function seedStrategy(
  api: ApiClient,
  siteId: string,
): Promise<SeededStrategy> {
  const resp = await api.post("api/v1/conversations", {
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

/** The one node running `searchName`. */
export function nodeBySearch(nodes: readonly AstNode[], searchName: string): AstNode {
  const matches = nodes.filter((node) => node.searchName === searchName);
  expect(matches, `exactly one ${searchName} step`).toHaveLength(1);
  return matches[0] as AstNode;
}

/** The one combine node whose operator is `operator`. */
export function combineWith(nodes: readonly AstNode[], operator: string): AstNode {
  const matches = nodes.filter(
    (node) => node.searchName === COMBINE_SEARCH_NAME && node.operator === operator,
  );
  expect(matches, `exactly one ${operator} combine`).toHaveLength(1);
  return matches[0] as AstNode;
}

const CARD_STEP = /^'(.+)' \(/;
const ASKED_STEP = /^Delete step '(.+)' \(/;

/** The title of every step a pending delete card says goes: its own, then the cascade's. */
export async function cardRemovals(approval: Locator): Promise<string[]> {
  const asked = ASKED_STEP.exec(
    (await approval.getByTestId("approval-card-title").textContent()) ?? "",
  );
  const cascade = await approval
    .getByTestId("approval-card-cascade-step")
    .allTextContents();
  return [asked?.[1] ?? "", ...cascade.map((line) => CARD_STEP.exec(line)?.[1] ?? "")];
}

/** The node with `id`. */
export function nodeById(nodes: readonly AstNode[], id: string): AstNode {
  const node = nodes.find((candidate) => candidate.id === id);
  if (node === undefined) throw new Error(`the tree holds no node ${id}`);
  return node;
}

/** A parameter's value as text, single or multi pick. */
export function paramText(node: AstNode, name: string): string {
  const param = node.parameters?.[name];
  if (param === undefined) return "";
  if (param.values !== undefined) return param.values.map(String).join(",");
  return String(param.value ?? "");
}

/** The names of every parameter the node stores, sorted. */
export function paramNames(node: AstNode): string[] {
  return Object.keys(node.parameters ?? {}).sort();
}

/** Build one arc on a fresh conversation of the site, and return its id. */
export async function buildOn(
  chatPage: ChatPage,
  siteId: string,
  message: string,
): Promise<string> {
  await chatPage.startOn(siteId);
  await chatPage.sendAndSettle(message);
  const id = chatPage.lastStrategyId;
  if (id === null) throw new Error("the conversation has no id");
  return id;
}

/** Open the canvas and wait for its topbar to report the strategy saved. */
export async function openCanvas(
  graphPage: GraphPage,
  siteId: string,
  conversationId: string,
): Promise<void> {
  await graphPage.goToStrategy(siteId, conversationId);
  await graphPage.expectStrategyTopbar();
  await expectCanvasSaved(graphPage);
}

/** The canvas topbar reports every edit saved. */
export async function expectCanvasSaved(graphPage: GraphPage): Promise<void> {
  await expect(graphPage.strategyPageSyncState).toHaveAttribute(
    "data-sync-state",
    "idle",
    { timeout: 30_000 },
  );
}

/** The words the recap arc's reply opens with. */
export const RECAP_REPLY = /This conversation already carries/;

/** Ask the strategy's count and assert the facts beside the reply show what the site answers. */
export async function expectCountAnswered(
  chatPage: ChatPage,
  api: ApiClient,
  conversationId: string,
  siteId: string,
): Promise<number> {
  await chatPage.sendAndSettle(prompt("recap", COUNT_QUESTION));
  const { root } = await siteCounts(api, conversationId, siteId);
  await expect(
    chatPage.assistantReply(RECAP_REPLY).and(chatPage.replyCounting(root)),
  ).not.toHaveCount(0);
  return root;
}

/** Record that the site refused or timed out a step save, so the report names the site. */
export function noteSiteRefusedSave(step: string): void {
  test.info().annotations.push({
    type: "site-refused-save",
    description: `The site refused or timed out the save of ${step}; the editor showed "Save failed".`,
  });
}
