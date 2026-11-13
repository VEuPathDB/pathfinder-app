import { afterEach, describe, expect, it } from "vitest";
import type { ConversationResponse } from "@strategist/shared";

import { strategyQueryOptions, toStrategy } from "@/lib/api/strategy";
import { createTestQueryClient } from "@/lib/query/testing";
import { useThreadModeStore } from "@/state/useThreadModeStore";

import { threadModeFor } from "./threadMode";

const queryClient = createTestQueryClient();

function seedDetail(id: string, detail: Partial<ConversationResponse>) {
  queryClient.setQueryData(
    strategyQueryOptions(id).queryKey,
    toStrategy({
      id,
      name: "t",
      siteId: "plasmodb",
      recordType: null,
      createdAt: "2026-11-06T00:00:00Z",
      updatedAt: "2026-11-06T00:00:00Z",
      ...detail,
    }),
  );
}

describe("threadModeFor", () => {
  afterEach(() => {
    useThreadModeStore.setState({ modes: {} });
    queryClient.clear();
  });

  it("prefers the pick over the kept mode", () => {
    seedDetail("c3", { mode: "build" });
    useThreadModeStore.getState().setMode("c3", "explore");
    expect(threadModeFor("c3", queryClient)).toBe("explore");
  });

  it("reads the kept mode when nothing was picked", () => {
    seedDetail("c4", { mode: "build" });
    expect(threadModeFor("c4", queryClient)).toBe("build");
  });

  it("is auto for a thread with no pick and no kept mode", () => {
    expect(threadModeFor("c5", queryClient)).toBe("auto");
  });
});
