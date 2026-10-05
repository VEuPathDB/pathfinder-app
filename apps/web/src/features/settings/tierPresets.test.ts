import { describe, expect, it } from "vitest";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import {
  applyTierPreset,
  deriveActiveTier,
  presetsForProvider,
  rolesForAssistant,
  CUSTOM_TIER,
} from "@/features/settings/tierPresets";
import {
  ANTHROPIC_SMALL,
  DEFAULT_MODEL,
  OPENAI_FLAGSHIP,
  OPENAI_SMALL,
} from "@/lib/models/__fixtures__/models";

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
    verification: worker,
  },
});

const STANDARD = cfg(DEFAULT_MODEL.id, "medium");
const SMALL = cfg(OPENAI_SMALL.id, "medium");
const SMALL_LOW = cfg(OPENAI_SMALL.id, "low");
const FLAGSHIP = cfg(OPENAI_FLAGSHIP.id, "high");

const DEFAULT_TIER = pathfinder(STANDARD, SMALL);
const QUALITY_TIER = pathfinder(FLAGSHIP, STANDARD);
const BALANCED_TIER = pathfinder(STANDARD, SMALL);
const FAST_TIER = pathfinder(SMALL_LOW, SMALL_LOW);

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
        cfg(ANTHROPIC_SMALL.id, "medium"),
        cfg(ANTHROPIC_SMALL.id, "medium"),
      ),
    },
  },
  site_help: {
    openai: {
      default: { roles: { site_help: SMALL } },
      quality: { roles: { site_help: STANDARD } },
      balanced: { roles: { site_help: SMALL } },
      fast: { roles: { site_help: SMALL_LOW } },
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
      "verification",
    ]);
    expect(rolesForAssistant(PRESETS, "site_help", "openai")).toEqual(["site_help"]);
  });

  it("names no role while the presets are loading", () => {
    expect(rolesForAssistant(undefined, "pathfinder", "openai")).toEqual([]);
  });
});

describe("applyTierPreset", () => {
  it("sets the model and effort of every role the researcher picks", () => {
    expect(applyTierPreset(QUALITY_TIER)).toEqual({
      models: {
        lead: OPENAI_FLAGSHIP.id,
        frame: OPENAI_FLAGSHIP.id,
        verification: DEFAULT_MODEL.id,
      },
      reasoning: {
        lead: "high",
        frame: "high",
        verification: "medium",
      },
    });
  });

  it("sets the one role of a one-agent assistant", () => {
    expect(applyTierPreset(PRESETS.site_help.openai.quality)).toEqual({
      models: { site_help: DEFAULT_MODEL.id },
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
    // Site help runs one model on default and fast; only effort separates
    // them, so a model-only comparison would conflate the two.
    const applied = applyTierPreset(PRESETS.site_help.openai.fast);
    expect(
      deriveActiveTier(
        PRESETS,
        "site_help",
        "openai",
        applied.models,
        applied.reasoning,
        "default",
      ),
    ).toBe("fast");
  });

  it("reads only the roles of the assistant it is asked about", () => {
    const applied = applyTierPreset(PRESETS.site_help.openai.fast);
    const mixed = { ...applyTierPreset(QUALITY_TIER).models, ...applied.models };
    const mixedReasoning = {
      ...applyTierPreset(QUALITY_TIER).reasoning,
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
    ).toBe("fast");
    expect(
      deriveActiveTier(
        PRESETS,
        "pathfinder",
        "openai",
        mixed,
        mixedReasoning,
        "default",
      ),
    ).toBe("quality");
  });

  it("recognises a preset when every role the researcher picks matches it", () => {
    // The repair role differs between quality and the deployment's default,
    // and the researcher has no row to pin it on.
    const models = {
      lead: OPENAI_FLAGSHIP.id,
      frame: OPENAI_FLAGSHIP.id,
      verification: DEFAULT_MODEL.id,
    };
    const reasoning = {
      lead: "high" as const,
      frame: "high" as const,
      verification: "medium" as const,
    };
    expect(
      deriveActiveTier(PRESETS, "pathfinder", "openai", models, reasoning, "default"),
    ).toBe("quality");
  });

  it("is custom when a single role model is changed", () => {
    const applied = applyTierPreset(QUALITY_TIER);
    const models = { ...applied.models, verification: OPENAI_FLAGSHIP.id };
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
    // site_help runs one config on default and balanced, so the picks alone
    // cannot separate them.
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
        { verification: OPENAI_FLAGSHIP.id },
        { verification: "high" },
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
    // The planning roles are unpinned, so the deployment tier decides whether
    // the pinned checking role completes the quality preset.
    const models = { verification: DEFAULT_MODEL.id };
    const reasoning = { verification: "medium" as const };
    expect(
      deriveActiveTier(PRESETS, "pathfinder", "openai", models, reasoning, "quality"),
    ).toBe("quality");
    expect(
      deriveActiveTier(PRESETS, "pathfinder", "openai", models, reasoning, "default"),
    ).toBe(CUSTOM_TIER);
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
