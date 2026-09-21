import { describe, expect, it } from "vitest";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import {
  applyTierPreset,
  deriveActiveTier,
  presetsForProvider,
  rolesForAssistant,
  CUSTOM_TIER,
} from "@/features/settings/tierPresets";

const cfg = (modelId: string, reasoningEffort: "low" | "medium" | "high") => ({
  modelId,
  reasoningEffort,
});

const pathfinder = (
  thinker: ReturnType<typeof cfg>,
  worker: ReturnType<typeof cfg>,
): TierPreset => ({
  roles: {
    lead: thinker,
    frame: thinker,
    execution: worker,
    verification: thinker,
  },
});

const LUNA = cfg("openai:gpt-5.6-luna", "medium");
const LUNA_LOW = cfg("openai:gpt-5.6-luna", "low");
const SOL = cfg("openai:gpt-5.6-sol", "high");
const TERRA = cfg("openai:gpt-5.6-terra", "medium");

const DEFAULT_TIER = pathfinder(LUNA, LUNA);
const QUALITY_TIER = pathfinder(SOL, TERRA);
const BALANCED_TIER = pathfinder(TERRA, LUNA);
const FAST_TIER = pathfinder(LUNA_LOW, LUNA_LOW);

const PRESETS = {
  pathfinder: {
    openai: {
      default: DEFAULT_TIER,
      quality: QUALITY_TIER,
      balanced: BALANCED_TIER,
      fast: FAST_TIER,
    },
    anthropic: {
      default: pathfinder(
        cfg("anthropic:claude-sonnet-5", "medium"),
        cfg("anthropic:claude-sonnet-5", "medium"),
      ),
    },
  },
  site_help: {
    openai: {
      default: { roles: { site_help: LUNA } },
      quality: { roles: { site_help: TERRA } },
      balanced: { roles: { site_help: LUNA } },
      fast: { roles: { site_help: LUNA_LOW } },
    },
  },
};

describe("presetsForProvider", () => {
  it("returns the tiers of one assistant on one provider", () => {
    expect(Object.keys(presetsForProvider(PRESETS, "pathfinder", "openai"))).toEqual([
      "default",
      "quality",
      "balanced",
      "fast",
    ]);
  });

  it("returns empty for an unknown assistant or provider rather than throwing", () => {
    expect(presetsForProvider(PRESETS, "curator", "openai")).toEqual({});
    expect(presetsForProvider(PRESETS, "pathfinder", "nope")).toEqual({});
  });

  it("returns empty when presets are still loading", () => {
    expect(presetsForProvider(undefined, "pathfinder", "openai")).toEqual({});
  });
});

describe("rolesForAssistant", () => {
  it("names the roles of the assistant in use, and nobody else's", () => {
    expect(rolesForAssistant(PRESETS, "pathfinder", "openai")).toEqual([
      "lead",
      "frame",
      "execution",
      "verification",
    ]);
    expect(rolesForAssistant(PRESETS, "site_help", "openai")).toEqual(["site_help"]);
  });

  it("names no role while the presets are loading", () => {
    expect(rolesForAssistant(undefined, "pathfinder", "openai")).toEqual([]);
  });
});

describe("applyTierPreset", () => {
  it("sets every role's model and effort from the preset", () => {
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

  it("sets the one role of a one-agent assistant", () => {
    expect(applyTierPreset(PRESETS.site_help.openai.quality)).toEqual({
      models: { site_help: "openai:gpt-5.6-terra" },
      reasoning: { site_help: "medium" },
    });
  });

  it("round-trips: applying a preset makes it the active tier", () => {
    const applied = applyTierPreset(QUALITY_TIER);
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        applied.models,
        applied.reasoning,
        "default",
      ),
    ).toBe("quality");
  });
});

describe("deriveActiveTier", () => {
  it("reports the tier whose every role matches", () => {
    const applied = applyTierPreset(DEFAULT_TIER);
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        applied.models,
        applied.reasoning,
        "default",
      ),
    ).toBe("default");
  });

  it("distinguishes tiers that differ only by reasoning effort", () => {
    // default and fast use the SAME model everywhere; only effort separates
    // them, so a model-only comparison would conflate the two.
    const applied = applyTierPreset(FAST_TIER);
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        applied.models,
        applied.reasoning,
        "default",
      ),
    ).toBe("fast");
  });

  it("reads only the roles of the assistant it is asked about", () => {
    const applied = applyTierPreset(PRESETS.site_help.openai.quality);
    const mixed = { ...applyTierPreset(FAST_TIER).models, ...applied.models };
    const mixedReasoning = {
      ...applyTierPreset(FAST_TIER).reasoning,
      ...applied.reasoning,
    };
    expect(
      deriveActiveTier(
        PRESETS,
        "site_help",
        "openai",
        mixed,
        mixedReasoning,
        "default",
      ),
    ).toBe("quality");
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        mixed,
        mixedReasoning,
        "default",
      ),
    ).toBe("fast");
  });

  it("is custom when a single role model is changed", () => {
    const applied = applyTierPreset(QUALITY_TIER);
    const models = { ...applied.models, execution: "openai:gpt-5.6-sol" };
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        models,
        applied.reasoning,
        "default",
      ),
    ).toBe(CUSTOM_TIER);
  });

  it("is custom when a single role effort is changed", () => {
    const applied = applyTierPreset(QUALITY_TIER);
    const reasoning = { ...applied.reasoning, frame: "low" as const };
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        applied.models,
        reasoning,
        "default",
      ),
    ).toBe(CUSTOM_TIER);
  });

  it("reports the deployment tier when nothing is pinned", () => {
    expect(deriveActiveTier(PRESETS, "pathfinder", "openai", {}, {}, "balanced")).toBe(
      "balanced",
    );
    expect(deriveActiveTier(PRESETS, "pathfinder", "openai", {}, {}, "default")).toBe(
      "default",
    );
  });

  it("prefers the deployment tier when two presets carry the same config", () => {
    // site_help runs the cheaper model on both default and balanced, so the
    // picks alone cannot separate them.
    expect(deriveActiveTier(PRESETS, "site_help", "openai", {}, {}, "balanced")).toBe(
      "balanced",
    );
    expect(deriveActiveTier(PRESETS, "site_help", "openai", {}, {}, "default")).toBe(
      "default",
    );
  });

  it("is custom when one pin leaves the deployment tier", () => {
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        { execution: "openai:gpt-5.6-sol" },
        { execution: "high" },
        "balanced",
      ),
    ).toBe(CUSTOM_TIER);
  });

  it("reports the preset the pins reach, deployment tier or not", () => {
    const applied = applyTierPreset(QUALITY_TIER);
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        applied.models,
        applied.reasoning,
        "balanced",
      ),
    ).toBe("quality");
  });

  it("fills a role no pin names from the deployment tier", () => {
    // Pinning the three reasoning roles onto terra, on a deployment whose
    // unpinned execution role already runs luna, is the balanced preset.
    const models = {
      lead: "openai:gpt-5.6-terra",
      frame: "openai:gpt-5.6-terra",
      verification: "openai:gpt-5.6-terra",
    };
    const reasoning = {
      lead: "medium" as const,
      frame: "medium" as const,
      verification: "medium" as const,
    };
    expect(
      deriveActiveTier(PRESETS, "pathfinder", "openai", models, reasoning, "default"),
    ).toBe("balanced");
  });

  it("is custom when a role is missing and the deployment tier is unknown", () => {
    const applied = applyTierPreset(DEFAULT_TIER);
    const { lead: _lead, ...partial } = applied.models;
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        partial,
        applied.reasoning,
        undefined,
      ),
    ).toBe(CUSTOM_TIER);
  });

  it("does not match a tier from a different provider", () => {
    // Anthropic's default has the same SHAPE; selecting openai must not match it.
    const applied = applyTierPreset(PRESETS.pathfinder.anthropic.default);
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        applied.models,
        applied.reasoning,
        "default",
      ),
    ).toBe(CUSTOM_TIER);
  });

  it("is custom when presets have not loaded", () => {
    const applied = applyTierPreset(DEFAULT_TIER);
    expect(
      deriveActiveTier(
        undefined,
        "pathfinder",
        "openai",
        applied.models,
        applied.reasoning,
        "default",
      ),
    ).toBe(CUSTOM_TIER);
  });

  it("is custom when the deployment names a tier the presets do not carry", () => {
    expect(deriveActiveTier(PRESETS, "pathfinder", "openai", {}, {}, "custom")).toBe(
      CUSTOM_TIER,
    );
  });
});
