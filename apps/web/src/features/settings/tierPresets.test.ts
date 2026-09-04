import { describe, expect, it } from "vitest";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import {
  applyTierPreset,
  deriveActiveTier,
  presetsForProvider,
  CUSTOM_TIER,
} from "@/features/settings/tierPresets";

const cfg = (modelId: string, reasoningEffort: "low" | "medium" | "high") => ({
  modelId,
  reasoningEffort,
});

const DEFAULT_TIER: TierPreset = {
  lead: cfg("openai:gpt-5.6-luna", "medium"),
  frame: cfg("openai:gpt-5.6-luna", "medium"),
  execution: cfg("openai:gpt-5.6-luna", "medium"),
  verification: cfg("openai:gpt-5.6-luna", "medium"),
};

const QUALITY_TIER: TierPreset = {
  lead: cfg("openai:gpt-5.6-sol", "high"),
  frame: cfg("openai:gpt-5.6-sol", "high"),
  execution: cfg("openai:gpt-5.6-terra", "medium"),
  verification: cfg("openai:gpt-5.6-sol", "high"),
};

const FAST_TIER: TierPreset = {
  lead: cfg("openai:gpt-5.6-luna", "low"),
  frame: cfg("openai:gpt-5.6-luna", "low"),
  execution: cfg("openai:gpt-5.6-luna", "low"),
  verification: cfg("openai:gpt-5.6-luna", "low"),
};

const PRESETS = {
  openai: { default: DEFAULT_TIER, quality: QUALITY_TIER, fast: FAST_TIER },
  anthropic: {
    default: {
      lead: cfg("anthropic:claude-sonnet-5", "medium"),
      frame: cfg("anthropic:claude-sonnet-5", "medium"),
      execution: cfg("anthropic:claude-sonnet-5", "medium"),
      verification: cfg("anthropic:claude-sonnet-5", "medium"),
    },
  },
};

describe("presetsForProvider", () => {
  it("returns the provider's tiers", () => {
    expect(Object.keys(presetsForProvider(PRESETS, "openai"))).toEqual([
      "default",
      "quality",
      "fast",
    ]);
  });

  it("returns empty for an unknown provider rather than throwing", () => {
    expect(presetsForProvider(PRESETS, "nope")).toEqual({});
  });

  it("returns empty when presets are still loading", () => {
    expect(presetsForProvider(undefined, "openai")).toEqual({});
  });
});

describe("applyTierPreset", () => {
  it("sets every phase's model and effort from the preset", () => {
    expect(applyTierPreset(QUALITY_TIER)).toEqual({
      models: {
        lead: "openai:gpt-5.6-sol",
        frame: "openai:gpt-5.6-sol",
        execution: "openai:gpt-5.6-terra",
        verification: "openai:gpt-5.6-sol",
      },
      reasoning: {
        lead: "high",
        frame: "high",
        execution: "medium",
        verification: "high",
      },
    });
  });

  it("round-trips: applying a preset makes it the active tier", () => {
    const applied = applyTierPreset(QUALITY_TIER);
    expect(deriveActiveTier(PRESETS, "openai", applied.models, applied.reasoning)).toBe(
      "quality",
    );
  });
});

describe("deriveActiveTier", () => {
  it("reports the tier whose every phase matches", () => {
    const applied = applyTierPreset(DEFAULT_TIER);
    expect(deriveActiveTier(PRESETS, "openai", applied.models, applied.reasoning)).toBe(
      "default",
    );
  });

  it("distinguishes tiers that differ only by reasoning effort", () => {
    // default and fast use the SAME model everywhere; only effort separates
    // them, so a model-only comparison would conflate the two.
    const applied = applyTierPreset(FAST_TIER);
    expect(deriveActiveTier(PRESETS, "openai", applied.models, applied.reasoning)).toBe(
      "fast",
    );
  });

  it("is custom when a single phase model is changed", () => {
    const applied = applyTierPreset(QUALITY_TIER);
    const models = { ...applied.models, execution: "openai:gpt-5.6-sol" };
    expect(deriveActiveTier(PRESETS, "openai", models, applied.reasoning)).toBe(
      CUSTOM_TIER,
    );
  });

  it("is custom when a single phase effort is changed", () => {
    const applied = applyTierPreset(QUALITY_TIER);
    const reasoning = { ...applied.reasoning, frame: "low" as const };
    expect(deriveActiveTier(PRESETS, "openai", applied.models, reasoning)).toBe(
      CUSTOM_TIER,
    );
  });

  it("is custom when nothing is pinned, since defaults come from the server", () => {
    expect(deriveActiveTier(PRESETS, "openai", {}, {})).toBe(CUSTOM_TIER);
  });

  it("is custom when a phase is missing from the selection", () => {
    const applied = applyTierPreset(DEFAULT_TIER);
    const { lead: _lead, ...partial } = applied.models;
    expect(deriveActiveTier(PRESETS, "openai", partial, applied.reasoning)).toBe(
      CUSTOM_TIER,
    );
  });

  it("does not match a tier from a different provider", () => {
    // Anthropic's default has the same SHAPE; selecting openai must not match it.
    const anthropicApplied = applyTierPreset(PRESETS.anthropic.default);
    expect(
      deriveActiveTier(
        PRESETS,
        "openai",
        anthropicApplied.models,
        anthropicApplied.reasoning,
      ),
    ).toBe(CUSTOM_TIER);
  });

  it("is custom when presets have not loaded", () => {
    const applied = applyTierPreset(DEFAULT_TIER);
    expect(
      deriveActiveTier(undefined, "openai", applied.models, applied.reasoning),
    ).toBe(CUSTOM_TIER);
  });
});
