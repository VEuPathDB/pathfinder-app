/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";

vi.mock("next/navigation", () => ({
  usePathname: () => "/plasmodb/conversation",
  useSearchParams: () => new URLSearchParams(),
}));

import { createTestWrapper } from "@/lib/query/testing";
import { useSettingsStore } from "@/state/useSettingsStore";

import { server } from "../../../../../vitest.msw-setup";
import { ModelSettings } from "./ModelSettings";
import {
  ANTHROPIC_FLAGSHIP,
  ANTHROPIC_SMALL,
  DEFAULT_MODEL,
} from "@/lib/models/__fixtures__/models";

const BASE = "http://localhost:3000/pathfinder";

function uniform(modelId: string, reasoningEffort = "medium") {
  const config = { modelId, reasoningEffort };
  return {
    roles: { lead: config, frame: config, execution: config, verification: config },
  };
}

const TIERS = {
  presets: {
    pathfinder: {
      openai: { default: uniform(DEFAULT_MODEL.id) },
      anthropic: { quality: uniform(ANTHROPIC_SMALL.id) },
    },
  },
  ownKeyPresets: {
    pathfinder: {
      openai: { default: uniform(DEFAULT_MODEL.id) },
      anthropic: { quality: uniform(ANTHROPIC_FLAGSHIP.id) },
    },
  },
};

const CATALOG = {
  models: [
    {
      id: DEFAULT_MODEL.id,
      name: DEFAULT_MODEL.name,
      provider: "openai",
      modelName: DEFAULT_MODEL.modelName,
      rank: "standard",
      deploymentMayPay: true,
      enabled: true,
      supportsReasoning: true,
    },
    {
      id: ANTHROPIC_SMALL.id,
      name: ANTHROPIC_SMALL.name,
      provider: "anthropic",
      modelName: ANTHROPIC_SMALL.modelName,
      rank: "small",
      deploymentMayPay: true,
      enabled: false,
    },
    {
      id: ANTHROPIC_FLAGSHIP.id,
      name: ANTHROPIC_FLAGSHIP.name,
      provider: "anthropic",
      modelName: ANTHROPIC_FLAGSHIP.modelName,
      rank: "flagship",
      deploymentMayPay: false,
      enabled: false,
    },
  ],
  defaultProvider: "openai",
  defaultTier: "default",
  phaseDefaults: {
    lead: DEFAULT_MODEL.id,
    frame: DEFAULT_MODEL.id,
    execution: DEFAULT_MODEL.id,
    verification: DEFAULT_MODEL.id,
  },
};

let payers: Record<string, string> = { openai: "deployment", anthropic: "user" };

beforeEach(() => {
  useSettingsStore.getState().resetToDefaults();
  server.use(
    http.get(`${BASE}/api/v1/models`, () => HttpResponse.json(CATALOG)),
    http.get(`${BASE}/api/v1/tiers`, () => HttpResponse.json(TIERS)),
    http.get(`${BASE}/api/v1/me/provider-keys`, () =>
      HttpResponse.json({ enabled: true, keys: [], payers }),
    ),
  );
});

afterEach(() => {
  payers = { openai: "deployment", anthropic: "user" };
});

const HIGH = { lead: "high", frame: "high", verification: "high" } as const;

function picksOf(modelId: string) {
  return { lead: modelId, frame: modelId, verification: modelId };
}

function useTwoProviderTiers() {
  const presets = {
    pathfinder: {
      openai: {
        default: uniform(DEFAULT_MODEL.id),
        quality: uniform(DEFAULT_MODEL.id, "high"),
      },
      anthropic: {
        default: uniform(ANTHROPIC_SMALL.id),
        quality: uniform(ANTHROPIC_FLAGSHIP.id, "high"),
      },
    },
  };
  server.use(
    http.get(`${BASE}/api/v1/tiers`, () =>
      HttpResponse.json({ presets, ownKeyPresets: presets }),
    ),
  );
}

function renderSettings() {
  const { Wrapper } = createTestWrapper();
  return render(<ModelSettings />, { wrapper: Wrapper });
}

describe("ModelSettings providers", () => {
  it("offers the presets of a provider the researcher's key pays for", async () => {
    renderSettings();

    fireEvent.click(await screen.findByRole("radio", { name: "Anthropic" }));

    expect(await screen.findByRole("button", { name: "Quality" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Default" })).toBeNull();
  });

  it("applies a preset on the researcher's key to every stage", async () => {
    renderSettings();

    fireEvent.click(await screen.findByRole("radio", { name: "Anthropic" }));
    fireEvent.click(await screen.findByRole("button", { name: "Quality" }));

    expect(useSettingsStore.getState().phaseModels["lead"]).toBe(ANTHROPIC_FLAGSHIP.id);
  });

  it("applies the deployment's Anthropic preset when no key of the researcher pays", async () => {
    payers = { openai: "deployment", anthropic: "deployment" };
    renderSettings();

    fireEvent.click(await screen.findByRole("radio", { name: "Anthropic" }));
    fireEvent.click(await screen.findByRole("button", { name: "Quality" }));

    expect(useSettingsStore.getState().phaseModels["lead"]).toBe(ANTHROPIC_SMALL.id);
  });

  it("moves the stages to the same preset on the new provider", async () => {
    useTwoProviderTiers();
    useSettingsStore.getState().applyPhasePreset(picksOf(DEFAULT_MODEL.id), HIGH);
    renderSettings();

    fireEvent.click(await screen.findByRole("radio", { name: "Anthropic" }));

    expect(useSettingsStore.getState().phaseModels).toEqual(
      picksOf(ANTHROPIC_FLAGSHIP.id),
    );
    expect(useSettingsStore.getState().phaseReasoning).toEqual(HIGH);
    expect(await screen.findByRole("button", { name: "Quality" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("moves a custom setup to the new provider's default preset", async () => {
    useTwoProviderTiers();
    useSettingsStore
      .getState()
      .applyPhasePreset(picksOf(DEFAULT_MODEL.id), { ...HIGH, frame: "low" });
    renderSettings();

    fireEvent.click(await screen.findByRole("radio", { name: "Anthropic" }));

    expect(useSettingsStore.getState().phaseModels).toEqual(
      picksOf(ANTHROPIC_SMALL.id),
    );
    expect(await screen.findByRole("button", { name: "Default" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("opens on the provider the stages run on", async () => {
    useTwoProviderTiers();
    useSettingsStore.getState().applyPhasePreset(picksOf(ANTHROPIC_FLAGSHIP.id), HIGH);
    renderSettings();

    expect(await screen.findByRole("radio", { name: "Anthropic" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(await screen.findByRole("button", { name: "Quality" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("offers one stop for two presets that run the same models", async () => {
    const presets = {
      pathfinder: {
        openai: {
          default: uniform(DEFAULT_MODEL.id),
          balanced: uniform(DEFAULT_MODEL.id),
          quality: uniform(DEFAULT_MODEL.id, "high"),
        },
      },
    };
    server.use(
      http.get(`${BASE}/api/v1/tiers`, () =>
        HttpResponse.json({ presets, ownKeyPresets: presets }),
      ),
    );
    renderSettings();

    expect(await screen.findByRole("button", { name: "Default" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByRole("button", { name: "Balanced" })).toBeNull();
    expect(screen.getByRole("slider", { name: "Preset" })).toHaveAttribute(
      "aria-valuemax",
      "1",
    );
  });

  it("offers no provider choice when only the deployment pays", async () => {
    payers = { openai: "deployment" };
    renderSettings();

    expect(await screen.findByRole("button", { name: "Default" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Anthropic" })).toBeNull();
  });
});

describe("ModelSettings stages", () => {
  it("shows a row for Assistant, Planning and Checking, and none for the repair role", async () => {
    renderSettings();

    const rows = await screen.findAllByTestId(/^phase-row-/);
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "phase-row-lead",
      "phase-row-frame",
      "phase-row-verification",
    ]);
    expect(rows[0]).toHaveTextContent(/^Assistant/);
    expect(rows[1]).toHaveTextContent(/^Planning/);
    expect(rows[2]).toHaveTextContent(/^Checking/);
    expect(screen.queryByText("Building")).toBeNull();
  });
});

describe("ModelSettings stage controls", () => {
  it("gives each stage a reasoning slider, and names the stage's job on hover", async () => {
    renderSettings();

    const row = await screen.findByTestId("phase-row-lead");
    expect(
      await within(row).findByRole("slider", { name: "Reasoning effort" }),
    ).toHaveAttribute("aria-valuetext", "Medium");
    expect(within(row).getByText("Assistant")).toHaveAttribute("title");
  });
});

describe("ModelSettings preset match", () => {
  it("marks a preset as active when the three rows match it", async () => {
    const high = { modelId: DEFAULT_MODEL.id, reasoningEffort: "high" };
    const presets = {
      pathfinder: {
        openai: {
          default: uniform(DEFAULT_MODEL.id),
          quality: {
            roles: {
              lead: high,
              frame: high,
              execution: { modelId: DEFAULT_MODEL.id, reasoningEffort: "low" },
              verification: high,
            },
          },
        },
      },
    };
    server.use(
      http.get(`${BASE}/api/v1/tiers`, () =>
        HttpResponse.json({ presets, ownKeyPresets: presets }),
      ),
    );
    const picks = {
      lead: DEFAULT_MODEL.id,
      frame: DEFAULT_MODEL.id,
      verification: DEFAULT_MODEL.id,
    };
    useSettingsStore
      .getState()
      .applyPhasePreset(picks, { lead: "high", frame: "high", verification: "high" });
    renderSettings();

    const quality = await screen.findByRole("button", { name: "Quality" });
    expect(quality).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText(/don't match a preset/)).toBeNull();
  });
});

describe("ModelSettings stage defaults", () => {
  it("names a stage's default model by its display name", async () => {
    renderSettings();

    const row = await screen.findByTestId("phase-row-lead");
    expect(await within(row).findByText(/^Default:/)).toHaveTextContent(
      `Default: ${DEFAULT_MODEL.name}`,
    );
  });
});
