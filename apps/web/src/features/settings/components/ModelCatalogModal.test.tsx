// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ModelCatalogModal } from "./ModelCatalogModal";
import { ANTHROPIC_SMALL, DEFAULT_MODEL } from "@/lib/models/__fixtures__/models";

const BASE = "http://localhost:3000/pathfinder";

const CATALOG = {
  models: [
    {
      id: DEFAULT_MODEL.id,
      name: DEFAULT_MODEL.name,
      description: "Default model",
      supportsReasoning: true,
      contextSize: 400000,
      inputPrice: 1.25,
      cachedInputPrice: 0.75,
      outputPrice: 10,
      rank: "standard",
      provider: "openai",
      modelName: DEFAULT_MODEL.modelName,
      enabled: true,
      supportsImages: true,
      supportsDocuments: true,
    },
    {
      id: ANTHROPIC_SMALL.id,
      name: ANTHROPIC_SMALL.name,
      description: "Deep reasoning",
      supportsReasoning: true,
      contextSize: 200000,
      inputPrice: 15,
      cachedInputPrice: 1.5,
      outputPrice: 75,
      rank: "small",
      provider: "anthropic",
      modelName: ANTHROPIC_SMALL.modelName,
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
    await screen.findByText(ANTHROPIC_SMALL.name);

    expect(
      await within(row(ANTHROPIC_SMALL.name)).findByText("your key"),
    ).toBeInTheDocument();
    expect(
      within(row(ANTHROPIC_SMALL.name)).getByRole("button", { name: /Select/ }),
    ).toBeEnabled();
    expect(within(row(DEFAULT_MODEL.name)).queryByText("your key")).toBeNull();
  });

  it("keeps the deployment's view for a reader with no payers", async () => {
    keys = new Response(null, { status: 401 });
    render(<ModelCatalogModal open onOpenChange={() => {}} onSelect={() => {}} />);

    await screen.findByText(ANTHROPIC_SMALL.name);
    expect(
      within(row(ANTHROPIC_SMALL.name)).getByRole("button", { name: /Select/ }),
    ).toBeDisabled();
    expect(
      within(row(DEFAULT_MODEL.name)).getByRole("button", { name: /Select/ }),
    ).toBeEnabled();
  });
});

describe("ModelCatalogModal file support", () => {
  it("says which models read images and PDFs", async () => {
    render(<ModelCatalogModal open onOpenChange={() => {}} />);
    const luna = (await screen.findByText(DEFAULT_MODEL.name)).closest("tr");
    const opus = screen.getByText(ANTHROPIC_SMALL.name).closest("tr");
    if (luna === null || opus === null) throw new Error("no model rows");
    expect(within(luna).getByText("reads images and PDFs")).toBeInTheDocument();
    expect(within(opus).queryByText(/reads/)).toBeNull();
  });
});
