/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

vi.mock("next/navigation", () => ({
  usePathname: () => "/plasmodb/conversation",
  useSearchParams: () => new URLSearchParams(),
}));

import { createTestWrapper } from "@/lib/query/testing";
import { useSettingsStore } from "@/state/useSettingsStore";

import { server } from "../../../../vitest.msw-setup";
import {
  QuotaExhaustedBanner,
  RefusedKeyBanner,
  useComposerBlock,
} from "./QuotaExhaustedBanner";

const BASE = "http://localhost:3000";
const CONVERSATION = "c0ffee00-0000-4000-8000-000000000001";
const LUNA = "openai:gpt-5.6-luna";
const OPUS = "anthropic:claude-opus-5";
const ROLES = ["lead", "frame", "execution", "verification"];

function preset(modelId: string) {
  const config = { modelId, reasoningEffort: "medium" };
  return { roles: Object.fromEntries(ROLES.map((role) => [role, config])) };
}

const SPENT = {
  usedUsd: "10.00",
  limitUsd: "10.00",
  totalTokens: 900,
  percent: 100,
  resetsAt: "2026-10-01T00:00:00Z",
  ownKeyUsd: "0",
  ownKeyTokens: 0,
  ownKeyProviders: ["anthropic"],
};

interface Keys {
  enabled: boolean;
  keys: { provider: string; hint: string; status: string; createdAt: string }[];
  payers: Record<string, string>;
}

let keys: Keys = { enabled: true, keys: [], payers: {} };

beforeEach(() => {
  useSettingsStore.getState().resetToDefaults();
  server.use(
    http.get(`${BASE}/api/v1/me/quota`, () => HttpResponse.json(SPENT)),
    http.get(`${BASE}/api/v1/me/provider-keys`, () => HttpResponse.json(keys)),
    http.get(`${BASE}/api/v1/tiers`, () =>
      HttpResponse.json({
        presets: { pathfinder: { openai: { default: preset(LUNA) } } },
      }),
    ),
    http.get(`${BASE}/api/v1/models`, () =>
      HttpResponse.json({
        models: [],
        defaultProvider: "openai",
        defaultTier: "default",
        phaseDefaults: Object.fromEntries(ROLES.map((role) => [role, LUNA])),
      }),
    ),
  );
});

afterEach(() => {
  keys = { enabled: true, keys: [], payers: {} };
});

function Probe() {
  const block = useComposerBlock(CONVERSATION);
  return (
    <div>
      <QuotaExhaustedBanner conversationId={CONVERSATION} />
      <RefusedKeyBanner conversationId={CONVERSATION} />
      <span data-testid="blocked">{String(block.blocked)}</span>
    </div>
  );
}

async function renderProbe() {
  const { queryClient, Wrapper } = createTestWrapper();
  render(<Probe />, { wrapper: Wrapper });
  // Every read the block depends on has answered before a test reads it.
  await waitFor(() =>
    expect(
      queryClient
        .getQueryCache()
        .getAll()
        .filter((query) => query.state.status === "success").length,
    ).toBe(4),
  );
}

describe("the composer's payment block", () => {
  it("blocks a spent allowance while the deployment pays for a stage", async () => {
    keys = { enabled: true, keys: [], payers: { openai: "deployment" } };
    await renderProbe();

    expect(await screen.findByTestId("quota-exhausted-banner")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("blocked")).toHaveTextContent("true"),
    );
  });

  it("lets a turn every stage of which runs on the researcher's keys through", async () => {
    keys = {
      enabled: true,
      keys: [],
      payers: { openai: "deployment", anthropic: "user" },
    };
    useSettingsStore
      .getState()
      .applyPhasePreset(Object.fromEntries(ROLES.map((role) => [role, OPUS])), {});
    await renderProbe();

    expect(screen.getByTestId("blocked")).toHaveTextContent("false");
    expect(screen.queryByTestId("quota-exhausted-banner")).toBeNull();
  });

  it("blocks a turn a refused key would pay for, and says which key", async () => {
    keys = {
      enabled: true,
      keys: [
        {
          provider: "openai",
          hint: "WXYZ",
          status: "refused",
          createdAt: "2026-09-24T08:00:00Z",
        },
      ],
      payers: {},
    };
    await renderProbe();

    expect(
      await screen.findByText(
        "OpenAI refused the key you added. Replace or remove it in Settings, under Provider keys.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("blocked")).toHaveTextContent("true");
  });
});
