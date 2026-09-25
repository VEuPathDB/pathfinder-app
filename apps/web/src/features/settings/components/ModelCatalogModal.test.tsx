// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ModelCatalogModal } from "./ModelCatalogModal";

const BASE = "http://localhost:3000";

const CATALOG = {
  models: [
    {
      id: "openai:gpt-5.6-luna",
      name: "GPT-5.6 Luna",
      description: "Default model",
      supportsReasoning: true,
      contextSize: 400000,
      inputPrice: 1.25,
      cachedInputPrice: 0.75,
      outputPrice: 10,
      isProviderSmallest: false,
      provider: "openai",
      modelName: "gpt-5.6-luna",
      enabled: true,
      supportsImages: true,
      supportsDocuments: true,
    },
    {
      id: "anthropic:claude-opus-5",
      name: "Claude Opus 5",
      description: "Deep reasoning",
      supportsReasoning: true,
      contextSize: 200000,
      inputPrice: 15,
      cachedInputPrice: 1.5,
      outputPrice: 75,
      isProviderSmallest: false,
      provider: "anthropic",
      modelName: "claude-opus-5",
      enabled: false,
    },
  ],
  defaultProvider: "openai",
  defaultTier: "default",
  phaseDefaults: {},
};

let keys:
  Response | { enabled: boolean; keys: never[]; payers: Record<string, string> } = {
  enabled: true,
  keys: [],
  payers: { openai: "deployment", anthropic: "user" },
};

const server = setupServer(
  http.get(`${BASE}/api/v1/models`, () => HttpResponse.json(CATALOG)),
  http.get(`${BASE}/api/v1/me/provider-keys`, () =>
    keys instanceof Response ? keys : HttpResponse.json(keys),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ModelCatalogModal", () => {
  it("prices the cached-input column from the primary token", async () => {
    render(<ModelCatalogModal open onOpenChange={() => {}} />);
    const cell = await screen.findByText("$0.75");
    expect(cell).toHaveClass("text-primary/80");
    expect(cell.className).not.toContain("sky");
  });
});

describe("ModelCatalogModal payers", () => {
  function row(name: string): HTMLElement {
    const cell = screen.getByText(name);
    const tr = cell.closest("tr");
    if (tr === null) throw new Error(`no row for ${name}`);
    return tr;
  }

  it("offers a provider the researcher's key pays for, with a badge", async () => {
    keys = {
      enabled: true,
      keys: [],
      payers: { openai: "deployment", anthropic: "user" },
    };
    render(<ModelCatalogModal open onOpenChange={() => {}} onSelect={() => {}} />);
    await screen.findByText("Claude Opus 5");

    expect(
      await within(row("Claude Opus 5")).findByText("your key"),
    ).toBeInTheDocument();
    expect(
      within(row("Claude Opus 5")).getByRole("button", { name: /Select/ }),
    ).toBeEnabled();
    expect(within(row("GPT-5.6 Luna")).queryByText("your key")).toBeNull();
  });

  it("keeps the deployment's view for a reader with no payers", async () => {
    keys = new Response(null, { status: 401 });
    render(<ModelCatalogModal open onOpenChange={() => {}} onSelect={() => {}} />);

    await screen.findByText("Claude Opus 5");
    expect(
      within(row("Claude Opus 5")).getByRole("button", { name: /Select/ }),
    ).toBeDisabled();
    expect(
      within(row("GPT-5.6 Luna")).getByRole("button", { name: /Select/ }),
    ).toBeEnabled();
  });
});

describe("ModelCatalogModal file support", () => {
  it("says which models read images and PDFs", async () => {
    render(<ModelCatalogModal open onOpenChange={() => {}} />);
    const luna = (await screen.findByText("GPT-5.6 Luna")).closest("tr");
    const opus = screen.getByText("Claude Opus 5").closest("tr");
    if (luna === null || opus === null) throw new Error("no model rows");
    expect(within(luna).getByText("reads images and PDFs")).toBeInTheDocument();
    expect(within(opus).queryByText(/reads/)).toBeNull();
  });
});
