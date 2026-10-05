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
import { ANTHROPIC_SMALL, DEFAULT_MODEL } from "@/lib/models/__fixtures__/models";

const BASE = "http://localhost:3000";

function uniform(modelId: string) {
  const config = { modelId, reasoningEffort: "medium" };
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
};

const CATALOG = {
  models: [
    {
      id: DEFAULT_MODEL.id,
      name: DEFAULT_MODEL.name,
      provider: "openai",
      modelName: DEFAULT_MODEL.modelName,
      rank: "standard",
      enabled: true,
    },
    {
      id: ANTHROPIC_SMALL.id,
      name: ANTHROPIC_SMALL.name,
      provider: "anthropic",
      modelName: ANTHROPIC_SMALL.modelName,
      rank: "small",
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

function renderSettings() {
  const { Wrapper } = createTestWrapper();
  return render(<ModelSettings />, { wrapper: Wrapper });
}

describe("ModelSettings providers", () => {
  it("offers the presets of a provider the researcher's key pays for", async () => {
    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Anthropic" }));

    expect(await screen.findByRole("button", { name: "Quality" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Default" })).toBeNull();
  });

  it("applies a preset on the researcher's key to every stage", async () => {
    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Anthropic" }));
    fireEvent.click(await screen.findByRole("button", { name: "Quality" }));

    expect(useSettingsStore.getState().phaseModels["lead"]).toBe(ANTHROPIC_SMALL.id);
  });

  it("offers no provider choice when only the deployment pays", async () => {
    payers = { openai: "deployment" };
    renderSettings();

    expect(await screen.findByRole("button", { name: "Default" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Anthropic" })).toBeNull();
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

describe("ModelSettings preset match", () => {
  it("marks a preset as active when the three rows match it", async () => {
    const high = { modelId: DEFAULT_MODEL.id, reasoningEffort: "high" };
    server.use(
      http.get(`${BASE}/api/v1/tiers`, () =>
        HttpResponse.json({
          presets: {
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
          },
        }),
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
