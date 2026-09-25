/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { createTestWrapper } from "@/lib/query/testing";

import { server } from "../../../../../vitest.msw-setup";

import { ProviderKeySettings } from "./ProviderKeySettings";

const SENTINEL = "sk-proj-sentinel-0123456789WXYZ";
const KEYS_URL = "http://localhost:3000/api/v1/me/provider-keys";
interface StoredKey {
  provider: string;
  hint: string;
  status: string;
  refusal: string | null;
  createdAt: string;
  refusedAt: string | null;
}

const STORED: StoredKey = {
  provider: "openai",
  hint: "WXYZ",
  status: "active",
  refusal: null,
  createdAt: "2026-09-24T08:00:00Z",
  refusedAt: null,
};
const REFUSAL =
  "OpenAI refused the key you added, so nothing ran on it. Replace or remove your OpenAI key in Settings, under Provider keys.";

interface Listing {
  enabled: boolean;
  keys: StoredKey[];
  payers: Record<string, string>;
}

let listing: Listing = { enabled: true, keys: [], payers: { openai: "deployment" } };
const sent: { method: string; url: string; body: string }[] = [];

const handlers = [
  http.get(KEYS_URL, () => HttpResponse.json(listing)),
  http.put(`${KEYS_URL}/:provider`, async ({ request, params }) => {
    const body = await request.text();
    sent.push({ method: "PUT", url: request.url, body });
    if (params["provider"] === "anthropic") {
      return HttpResponse.json(
        {
          type: "about:blank",
          title: "OpenAI refused your key",
          status: 422,
          detail: REFUSAL,
          code: "PROVIDER_KEY_REFUSED",
        },
        { status: 422 },
      );
    }
    listing = { ...listing, keys: [STORED], payers: { openai: "user" } };
    return HttpResponse.json(STORED);
  }),
  http.delete(`${KEYS_URL}/:provider`, ({ request }) => {
    sent.push({ method: "DELETE", url: request.url, body: "" });
    listing = { ...listing, keys: [], payers: { openai: "deployment" } };
    return new HttpResponse(null, { status: 204 });
  }),
];

beforeEach(() => server.use(...handlers));
afterEach(() => {
  sent.length = 0;
  listing = { enabled: true, keys: [], payers: { openai: "deployment" } };
});

function renderTab() {
  const { queryClient, Wrapper } = createTestWrapper();
  const view = render(<ProviderKeySettings />, { wrapper: Wrapper });
  return { queryClient, view };
}

function caches(queryClient: ReturnType<typeof createTestWrapper>["queryClient"]) {
  return JSON.stringify([
    queryClient
      .getQueryCache()
      .getAll()
      .map((q) => q.state),
    queryClient
      .getMutationCache()
      .getAll()
      .map((m) => m.state),
  ]);
}

describe("ProviderKeySettings", () => {
  it("sends the key once and keeps it nowhere after", async () => {
    const { queryClient, view } = renderTab();
    const field = await screen.findByLabelText("OpenAI key");

    fireEvent.change(field, { target: { value: SENTINEL } });
    fireEvent.click(screen.getByRole("button", { name: "Save OpenAI key" }));

    await screen.findByText(/\.\.\.WXYZ, added/);
    expect(sent).toEqual([
      {
        method: "PUT",
        url: `${KEYS_URL}/openai`,
        body: JSON.stringify({ key: SENTINEL }),
      },
    ]);
    expect(screen.getByLabelText("OpenAI key")).toHaveValue("");
    expect(view.container.innerHTML).not.toContain(SENTINEL);
    await waitFor(() => expect(caches(queryClient)).not.toContain(SENTINEL));
  });

  it("types the key into a field that neither shows nor remembers it", async () => {
    renderTab();
    const field = await screen.findByLabelText("OpenAI key");

    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAttribute("autocomplete", "off");
    expect(field).toHaveAttribute("spellcheck", "false");
  });

  it("shows the server's sentence when the provider refuses the key", async () => {
    const { queryClient } = renderTab();
    const field = await screen.findByLabelText("Anthropic key");

    fireEvent.change(field, { target: { value: SENTINEL } });
    fireEvent.click(screen.getByRole("button", { name: "Save Anthropic key" }));

    expect(await screen.findByText(REFUSAL)).toBeInTheDocument();
    expect(screen.getByLabelText("Anthropic key")).toHaveValue("");
    await waitFor(() => expect(caches(queryClient)).not.toContain(SENTINEL));
  });

  it("removes a stored key", async () => {
    listing = { enabled: true, keys: [STORED], payers: { openai: "user" } };
    renderTab();

    fireEvent.click(await screen.findByRole("button", { name: "Remove OpenAI key" }));

    await waitFor(() =>
      expect(sent).toEqual([{ method: "DELETE", url: `${KEYS_URL}/openai`, body: "" }]),
    );
    await waitFor(() => expect(screen.queryByText(/\.\.\.WXYZ, added/)).toBeNull());
  });

  it("shows a refused key with what to do about it", async () => {
    listing = {
      enabled: true,
      keys: [
        {
          ...STORED,
          status: "refused",
          refusal: "invalid",
          refusedAt: "2026-09-24T09:00:00Z",
        },
      ],
      payers: {},
    };
    renderTab();

    expect(
      await screen.findByText(
        "...WXYZ was refused by OpenAI. Replace it or remove it.",
      ),
    ).toBeInTheDocument();
  });

  it.each([
    [
      "no_credit",
      "...WXYZ: This key has no credit. Add credit to the OpenAI account, or replace the key.",
    ],
    [
      "forbidden",
      "...WXYZ is not permitted by OpenAI to run its models. Replace it or remove it.",
    ],
  ])("says why a key refused as %s cannot pay", async (refusal, sentence) => {
    listing = {
      enabled: true,
      keys: [
        { ...STORED, status: "refused", refusal, refusedAt: "2026-09-24T09:00:00Z" },
      ],
      payers: {},
    };
    renderTab();

    expect(await screen.findByText(sentence)).toBeInTheDocument();
  });

  it("says so when the deployment takes no personal key", async () => {
    listing = { enabled: false, keys: [], payers: { openai: "deployment" } };
    renderTab();

    expect(
      await screen.findByText("This deployment does not accept personal keys."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("OpenAI key")).toBeNull();
  });
});
