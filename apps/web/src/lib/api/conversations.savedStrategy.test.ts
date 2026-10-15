import { beforeEach, describe, expect, it, vi } from "vitest";

import { client } from "@/lib/api/client";
import { insertSavedStrategy } from "./conversations";

vi.mock("@/lib/api/client", () => ({
  client: vi.fn(() =>
    Promise.resolve({
      data: {
        wdkStrategyId: 7,
        insertedSavedWdkStrategyId: 11,
        insertedSavedName: "Alpha set",
        combineStepId: "step_root",
      },
    }),
  ),
}));

const mockClient = vi.mocked(client);

beforeEach(() => {
  mockClient.mockClear();
});

describe("insertSavedStrategy", () => {
  it("omits the operator when the saved strategy becomes the root", async () => {
    await insertSavedStrategy({
      conversationId: "c1",
      siteId: "plasmodb",
      targetStepId: "",
      savedWdkStrategyId: 11,
    });

    expect(mockClient).toHaveBeenCalledWith({
      method: "post",
      url: "/api/v1/conversations/c1/insert-saved",
      params: { siteId: "plasmodb" },
      data: { targetStepId: "", savedWdkStrategyId: 11 },
    });
  });
});
