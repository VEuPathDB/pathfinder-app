/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useSessionStore } from "./useSessionStore";

beforeEach(() => {
  useSessionStore.setState({
    selectedSite: "veupathdb",
    pickedSite: "veupathdb",
    pendingUserSubmission: null,
    chatResetCounter: 0,
    createdConversationId: null,
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

  it("setPickedSite records the site picked on a website that offers the picker", () => {
    useSessionStore.getState().setPickedSite("toxodb");
    expect(useSessionStore.getState().pickedSite).toBe("toxodb");
  });

  it("setPickedSite is a no-op for the site already picked", () => {
    const before = useSessionStore.getState();
    before.setPickedSite("veupathdb");
    expect(useSessionStore.getState()).toBe(before);
  });

  it("persists only the picked site", () => {
    useSessionStore.getState().setSelectedSite("plasmodb");
    useSessionStore.getState().setPickedSite("toxodb");
    const stored = window.localStorage.getItem("pathfinder-session-20260625") ?? "{}";
    expect(JSON.parse(stored).state).toEqual({ pickedSite: "toxodb" });
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

  it("markConversationCreated names the conversation that now has a row", () => {
    useSessionStore.getState().markConversationCreated("c1");
    expect(useSessionStore.getState().createdConversationId).toBe("c1");
  });

  it("markConversationCreated is a no-op for the conversation it already names", () => {
    useSessionStore.getState().markConversationCreated("c1");
    const before = useSessionStore.getState();
    before.markConversationCreated("c1");
    expect(useSessionStore.getState()).toBe(before);
  });
});
