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
      openai: { default: uniform("openai:gpt-5.6-luna") },
      anthropic: { quality: uniform("anthropic:claude-opus-5") },
    },
  },
};

const CATALOG = {
  models: [
    {
      id: "openai:gpt-5.6-luna",
      name: "GPT-5.6 Luna",
      provider: "openai",
      modelName: "gpt-5.6-luna",
      enabled: true,
    },
    {
      id: "anthropic:claude-opus-5",
      name: "Claude Opus 5",
      provider: "anthropic",
      modelName: "claude-opus-5",
      enabled: false,
    },
  ],
  defaultProvider: "openai",
  defaultTier: "default",
  phaseDefaults: {
    lead: "openai:gpt-5.6-luna",
    frame: "openai:gpt-5.6-luna",
    execution: "openai:gpt-5.6-luna",
    verification: "openai:gpt-5.6-luna",
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

    expect(useSettingsStore.getState().phaseModels["lead"]).toBe(
      "anthropic:claude-opus-5",
    );
  });

  it("offers no provider choice when only the deployment pays", async () => {
    payers = { openai: "deployment" };
    renderSettings();

    expect(await screen.findByRole("button", { name: "Default" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Anthropic" })).toBeNull();
  });
});

describe("ModelSettings stage defaults", () => {
  it("names a stage's default model by its display name", async () => {
    renderSettings();

    const row = await screen.findByTestId("phase-row-lead");
    expect(await within(row).findByText(/^Default:/)).toHaveTextContent(
      "Default: GPT-5.6 Luna",
    );
  });
});
