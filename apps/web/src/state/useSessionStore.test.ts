import { beforeEach, describe, expect, it } from "vitest";

import { useSessionStore } from "./useSessionStore";

beforeEach(() => {
  useSessionStore.setState({
    selectedSite: "veupathdb",
    pendingUserSubmission: null,
    chatResetCounter: 0,
  });
});

describe("state/useSessionStore", () => {
  it("setSelectedSite updates the selected site", () => {
    useSessionStore.getState().setSelectedSite("tritrypdb");
    expect(useSessionStore.getState().selectedSite).toBe("tritrypdb");
  });

  it("setSelectedSite is a no-op for the current site", () => {
    const before = useSessionStore.getState();
    before.setSelectedSite("veupathdb");
    expect(useSessionStore.getState()).toBe(before);
  });

  it("setPendingUserSubmission carries the conversation and the text", () => {
    useSessionStore
      .getState()
      .setPendingUserSubmission({ conversationId: "c1", content: "go" });
    const pending = useSessionStore.getState().pendingUserSubmission;
    expect(pending).toEqual({ conversationId: "c1", content: "go" });
  });

  it("bumpChatResetCounter increments monotonically", () => {
    useSessionStore.getState().bumpChatResetCounter();
    useSessionStore.getState().bumpChatResetCounter();
    expect(useSessionStore.getState().chatResetCounter).toBe(2);
  });
});
