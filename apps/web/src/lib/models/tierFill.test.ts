import { describe, expect, it } from "vitest";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import { picksFilledFromTier } from "./tierFill";
import { DEFAULT_MODEL, OPENAI_FLAGSHIP, OPENAI_SMALL } from "./__fixtures__/models";

const TERRA = "openai:gpt-6.1-terra";

const preset = (thinker: string, explore: string): TierPreset => ({
  roles: {
    lead: { modelId: thinker, reasoningEffort: "medium" },
    frame: { modelId: thinker, reasoningEffort: "medium" },
    execution: { modelId: OPENAI_SMALL.id, reasoningEffort: "medium" },
    verification: { modelId: OPENAI_SMALL.id, reasoningEffort: "high" },
    explore: { modelId: explore, reasoningEffort: "medium" },
  },
});

const BALANCED = preset(DEFAULT_MODEL.id, TERRA);
const QUALITY = preset(OPENAI_FLAGSHIP.id, OPENAI_FLAGSHIP.id);

const savedBalanced = {
  models: {
    lead: DEFAULT_MODEL.id,
    frame: DEFAULT_MODEL.id,
    verification: OPENAI_SMALL.id,
  },
  reasoning: {
    lead: "medium",
    frame: "medium",
    verification: "high",
  },
} as const;

describe("picksFilledFromTier", () => {
  it("gives a role the saved tier predates that tier's model", () => {
    const filled = picksFilledFromTier([QUALITY, BALANCED], savedBalanced);

    expect(filled.models).toEqual({ ...savedBalanced.models, explore: TERRA });
    expect(filled.reasoning).toEqual({ ...savedBalanced.reasoning, explore: "medium" });
  });

  it("leaves picks that match no tier as they are", () => {
    const custom = {
      models: { ...savedBalanced.models, lead: OPENAI_FLAGSHIP.id },
      reasoning: savedBalanced.reasoning,
    };

    expect(picksFilledFromTier([QUALITY, BALANCED], custom)).toBe(custom);
  });

  it("fills no role a researcher could already pick", () => {
    const leadOnly = {
      models: { lead: OPENAI_FLAGSHIP.id },
      reasoning: { lead: "medium" },
    } as const;

    expect(picksFilledFromTier([QUALITY, BALANCED], leadOnly)).toBe(leadOnly);
  });

  it("leaves a researcher with no picks on the deployment's tier", () => {
    const none = { models: {}, reasoning: {} };

    expect(picksFilledFromTier([QUALITY, BALANCED], none)).toBe(none);
  });

  it("keeps an explore pick the researcher made", () => {
    const picked = {
      models: { ...savedBalanced.models, explore: OPENAI_FLAGSHIP.id },
      reasoning: { ...savedBalanced.reasoning, explore: "high" },
    } as const;

    expect(picksFilledFromTier([QUALITY, BALANCED], picked)).toBe(picked);
  });
});
