import { describe, expect, it } from "vitest";

import {
  AUDIT_ASSISTANT_ID,
  ASSISTANT_CHOICES,
  DEFAULT_ASSISTANT_ID,
  assistantLabel,
  resolveAssistantId,
} from "./assistants";

describe("the assistants this deployment serves", () => {
  it("offers the default first", () => {
    expect(ASSISTANT_CHOICES.map((choice) => choice.id)).toEqual([
      DEFAULT_ASSISTANT_ID,
      AUDIT_ASSISTANT_ID,
    ]);
  });

  it("labels a known assistant and falls back to the id", () => {
    expect(assistantLabel(DEFAULT_ASSISTANT_ID)).toBe("Strategy builder");
    expect(assistantLabel(AUDIT_ASSISTANT_ID)).toBe("Gene model audit");
    expect(assistantLabel("curator")).toBe("curator");
  });
});

describe("resolveAssistantId", () => {
  it("keeps the assistant an existing thread was created with", () => {
    expect(
      resolveAssistantId({ existing: "helper", requested: DEFAULT_ASSISTANT_ID }),
    ).toBe("helper");
  });

  it("opens a new thread under the audit assistant", () => {
    expect(resolveAssistantId({ existing: null, requested: AUDIT_ASSISTANT_ID })).toBe(
      AUDIT_ASSISTANT_ID,
    );
  });

  it("takes the requested assistant when no thread exists yet", () => {
    expect(
      resolveAssistantId({ existing: null, requested: DEFAULT_ASSISTANT_ID }),
    ).toBe(DEFAULT_ASSISTANT_ID);
  });

  it("ignores an assistant this deployment does not serve", () => {
    expect(resolveAssistantId({ existing: null, requested: "curator" })).toBe(
      DEFAULT_ASSISTANT_ID,
    );
  });

  it("is the default when nothing names one", () => {
    expect(resolveAssistantId({})).toBe(DEFAULT_ASSISTANT_ID);
  });
});
