import { describe, it, expect } from "vitest";

import { buildChatRequestBody } from "./buildRequestBody";

describe("buildChatRequestBody", () => {
  it("throws if siteId is empty", () => {
    expect(() =>
      buildChatRequestBody({
        conversationId: "c1",
        siteId: "",
        id: "x",
        trigger: "submit-message",
        messages: [],
        baseBody: undefined,
      }),
    ).toThrow(/siteId is required/);
  });

  it("throws if siteId is whitespace only", () => {
    expect(() =>
      buildChatRequestBody({
        conversationId: "c1",
        siteId: "   ",
        id: "x",
        trigger: "submit-message",
        messages: [],
        baseBody: undefined,
      }),
    ).toThrow();
  });

  it("includes siteId, conversationId, id, trigger, messages when siteId is set", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
    });
    expect(out).toMatchObject({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
    });
  });

  it("merges base body fields under our overrides", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: { extra: "passthrough", conversationId: "should-be-overridden" },
    });
    expect(out["extra"]).toBe("passthrough");
    expect(out.conversationId).toBe("c1");
  });

  it("includes phaseModels and phaseReasoning when non-empty", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
      phaseModels: { lead: "openai:gpt-5.4", frame: "anthropic:claude-sonnet-4-6" },
      phaseReasoning: { lead: "high" },
    });
    expect(out["phaseModels"]).toEqual({
      lead: "openai:gpt-5.4",
      frame: "anthropic:claude-sonnet-4-6",
    });
    expect(out["phaseReasoning"]).toEqual({ lead: "high" });
  });

  it("names the assistant when the caller gives one", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
      assistantId: "site_help",
    });
    expect(out["assistantId"]).toBe("site_help");
  });

  it("omits the assistant when the caller names none", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
    });
    expect("assistantId" in out).toBe(false);
  });

  it("omits phaseModels and phaseReasoning when empty or missing", () => {
    const out = buildChatRequestBody({
      conversationId: "c1",
      siteId: "plasmodb",
      id: "x",
      trigger: "submit-message",
      messages: [],
      baseBody: undefined,
      phaseModels: {},
      phaseReasoning: {},
    });
    expect("phaseModels" in out).toBe(false);
    expect("phaseReasoning" in out).toBe(false);
  });
});
