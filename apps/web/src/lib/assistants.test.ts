import { describe, expect, it } from "vitest";

import {
  ASSISTANT_CHOICES,
  DEFAULT_ASSISTANT_ID,
  SITE_HELP_ASSISTANT_ID,
  assistantLabel,
  resolveAssistantId,
} from "./assistants";

describe("the assistants this deployment serves", () => {
  it("offers both of them, the default first", () => {
    expect(ASSISTANT_CHOICES.map((choice) => choice.id)).toEqual([
      DEFAULT_ASSISTANT_ID,
      SITE_HELP_ASSISTANT_ID,
    ]);
  });

  it("labels a known assistant and falls back to the id", () => {
    expect(assistantLabel(SITE_HELP_ASSISTANT_ID)).toBe("Site help");
    expect(assistantLabel("curator")).toBe("curator");
  });
});

describe("resolveAssistantId", () => {
  it("keeps the assistant an existing thread was created with", () => {
    expect(
      resolveAssistantId({
        existing: SITE_HELP_ASSISTANT_ID,
        requested: DEFAULT_ASSISTANT_ID,
      }),
    ).toBe(SITE_HELP_ASSISTANT_ID);
  });

  it("takes the requested assistant when no thread exists yet", () => {
    expect(
      resolveAssistantId({ existing: null, requested: SITE_HELP_ASSISTANT_ID }),
    ).toBe(SITE_HELP_ASSISTANT_ID);
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
