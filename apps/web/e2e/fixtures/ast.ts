import type { APIResponse } from "@playwright/test";
import { expect } from "@playwright/test";

/**
 * Reading the persisted strategy AST in a spec.
 *
 * Step ids are generated when a step is built, so a spec locates a node by what
 * it is - its search, its operator, its position - never by a literal id.
 */

interface ParamValue {
  value?: unknown;
  values?: unknown[];
}

export interface AstNode {
  id?: string;
  searchName?: string | null;
  operator?: string | null;
  displayName?: string | null;
  /** Set on a combine step whose input is a collapsed saved strategy. */
  expandedStrategyId?: number | null;
  parameters?: Record<string, ParamValue> | null;
  primaryInput?: AstNode | null;
  secondaryInput?: AstNode | null;
  [k: string]: unknown;
}

/** The sentinel search name WDK-less combine nodes carry. */
export const COMBINE_SEARCH_NAME = "__combine__";

function collect(value: unknown, out: AstNode[]): void {
  if (value === null || typeof value !== "object") return;
  const node = value as AstNode;
  if (typeof node.id === "string") out.push(node);
  for (const child of Object.values(node)) collect(child, out);
}

/** Every node of the AST payload, parents included. */
export async function astNodes(resp: APIResponse): Promise<AstNode[]> {
  expect(resp.status()).toBe(200);
  const out: AstNode[] = [];
  collect((await resp.json()) as unknown, out);
  return out;
}

/** The single leaf running `searchName`. Fails when there is not exactly one. */
export async function leafBySearch(
  resp: APIResponse,
  searchName: string,
): Promise<AstNode> {
  const matches = (await astNodes(resp)).filter((n) => n.searchName === searchName);
  expect(matches, `exactly one ${searchName} leaf in the AST`).toHaveLength(1);
  return matches[0] as AstNode;
}

/** The single combine node. Fails when there is not exactly one. */
export async function combineNode(resp: APIResponse): Promise<AstNode> {
  const matches = (await astNodes(resp)).filter(
    (n) => n.searchName === COMBINE_SEARCH_NAME,
  );
  expect(matches, "exactly one combine node in the AST").toHaveLength(1);
  return matches[0] as AstNode;
}

/** The id of the single leaf running `searchName`. */
export async function leafIdBySearch(
  resp: APIResponse,
  searchName: string,
): Promise<string> {
  return (await leafBySearch(resp, searchName)).id as string;
}

/** The id of the single combine node. */
export async function combineId(resp: APIResponse): Promise<string> {
  return (await combineNode(resp)).id as string;
}

/** Every combine node's operator, sorted. */
export async function combineOperators(resp: APIResponse): Promise<(string | null)[]> {
  return (await astNodes(resp))
    .filter((n) => n.searchName === COMBINE_SEARCH_NAME)
    .map((n) => n.operator ?? null)
    .sort();
}
