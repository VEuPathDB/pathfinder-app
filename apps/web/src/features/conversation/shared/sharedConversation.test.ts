import { describe, expect, it } from "vitest";

import { APIError } from "@/lib/api/http";

import type { SharedConversation } from "@strategist/shared/generated/types/SharedConversation";

import {
  SHARED_POLL_MS,
  sharedPollAfter,
  sharedRailSource,
  sharedRefusalOf,
  sharedRetry,
} from "./sharedConversation";
import { SHARED_CONTEXT } from "./sharedContextFixture";

function refusal(status: number, code: string): APIError {
  return new APIError("refused", {
    status,
    statusText: "",
    url: "/api/v1/shared/tok-1",
    data: { title: "refused", status, code },
  });
}

const GONE = refusal(404, "SHARE_NOT_FOUND");
const LOCKED = refusal(403, "SHARE_LOCKED");
const DOWN = refusal(502, "INTERNAL_ERROR");

describe("sharedRefusalOf", () => {
  it.each([
    [GONE, "gone"],
    [LOCKED, "locked"],
    [DOWN, "failed"],
    [new TypeError("network"), "failed"],
  ])("reads %s as %s", (error, expected) => {
    expect(sharedRefusalOf(error)).toBe(expected);
  });
});

describe("sharedRetry", () => {
  it("retries a failed read twice", () => {
    expect([0, 1, 2].map((count) => sharedRetry(count, DOWN))).toEqual([
      true,
      true,
      false,
    ]);
  });

  it("never retries a link that is gone or locked", () => {
    expect([sharedRetry(0, GONE), sharedRetry(0, LOCKED)]).toEqual([false, false]);
  });
});

describe("sharedPollAfter", () => {
  it("keeps polling after a read that failed", () => {
    expect(sharedPollAfter(DOWN)).toBe(SHARED_POLL_MS);
    expect(sharedPollAfter(null)).toBe(SHARED_POLL_MS);
  });

  it("stops polling a link that is gone or locked", () => {
    expect([sharedPollAfter(GONE), sharedPollAfter(LOCKED)]).toEqual([false, false]);
  });
});

describe("sharedRailSource", () => {
  const head: SharedConversation = {
    name: "kinases",
    siteId: "plasmodb",
    assistantId: "strategist",
    allowCopy: false,
    includeContext: true,
    strategyRevision: "r-1",
    cursor: 7,
    turnInFlight: false,
  };

  it("builds a rail source with no owner", () => {
    const source = sharedRailSource("tok-1", head, SHARED_CONTEXT);

    expect(source).toMatchObject({
      key: "shared:tok-1",
      siteId: "plasmodb",
      owner: null,
      activeTasks: [],
      privateInputs: { "s-list": ["ds_gene_ids"] },
    });
    expect(source.strategy?.steps.map((step) => step.estimatedSize)).toEqual([
      41, 1204, 12,
    ]);
    expect(source.study?.studyDisplayName).toBe(
      "Heat shock response in sensitive mutants (LRR5, DHC)",
    );
  });

  it("shows no study when the link shares none", () => {
    expect(
      sharedRailSource("tok-1", head, { ...SHARED_CONTEXT, study: null }).study,
    ).toBe(null);
  });
});
