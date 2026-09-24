/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { useSessionStore } from "@/state/useSessionStore";
import { server } from "../../../../vitest.msw-setup";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

import { GeneSearchSidebar } from "./GeneSearchSidebar";

const BASE = "http://localhost:3000/api/v1/sites/plasmodb";
const GENE_SETS = "http://localhost:3000/api/v1/gene-sets";

/** Answers each search with one gene whose id the search text names. */
function searchAnswers(genes: Record<string, string>): void {
  server.use(
    http.get(`${BASE}/genes/search`, ({ request }) => {
      const q = new URL(request.url).searchParams.get("q") ?? "";
      const geneId = genes[q];
      return HttpResponse.json({
        results:
          geneId === undefined
            ? []
            : [{ geneId, organism: "Plasmodium falciparum 3D7" }],
        totalCount: geneId === undefined ? 0 : 1,
      });
    }),
  );
}

function search(text: string): void {
  fireEvent.change(screen.getByPlaceholderText("Search genes..."), {
    target: { value: text },
  });
}

/** Selects the one listed gene and submits "Create gene set". */
async function createFromSelection(geneId: string): Promise<void> {
  await userEvent.click(
    await screen.findByRole(
      "checkbox",
      { name: `Select ${geneId}` },
      { timeout: 2000 },
    ),
  );
  await userEvent.click(screen.getByRole("button", { name: "Create gene set (1)" }));
  await userEvent.click(screen.getByRole("button", { name: "Add" }));
}

beforeEach(() => {
  useSessionStore.getState().setSelectedSite("plasmodb");
  server.use(
    http.get(`${BASE}/organisms`, () =>
      HttpResponse.json({ organisms: ["Plasmodium falciparum 3D7"] }),
    ),
  );
});

describe("GeneSearchSidebar", () => {
  it("reports a failed gene search once, with no toast", async () => {
    server.use(
      http.get(`${BASE}/genes/search`, () =>
        HttpResponse.json({ detail: "gene search failed" }, { status: 500 }),
      ),
    );
    render(<GeneSearchSidebar />, { wrapper: appQueryClientWrapper() });

    fireEvent.change(screen.getByPlaceholderText("Search genes..."), {
      target: { value: "kinase" },
    });

    expect(
      await screen.findByText("gene search failed", {}, { timeout: 2000 }),
    ).toBeVisible();
    expect(screen.getAllByText("gene search failed")).toHaveLength(1);
    expect(toastError).not.toHaveBeenCalled();
  });

  it("drops a failed create's error when the search changes", async () => {
    searchAnswers({ kinase: "PF3D7_0100100", protease: "PF3D7_0200200" });
    server.use(
      http.post(GENE_SETS, () =>
        HttpResponse.json({ detail: "gene set save failed" }, { status: 500 }),
      ),
    );
    render(<GeneSearchSidebar />, { wrapper: appQueryClientWrapper() });

    search("kinase");
    await createFromSelection("PF3D7_0100100");
    expect(await screen.findByText("gene set save failed")).toBeVisible();

    search("protease");

    expect(
      await screen.findByRole(
        "checkbox",
        { name: "Select PF3D7_0200200" },
        { timeout: 2000 },
      ),
    ).not.toBeChecked();
    expect(screen.queryByText("gene set save failed")).toBe(null);
  });

  it("drops a failed create's error when a second create starts", async () => {
    searchAnswers({ kinase: "PF3D7_0100100" });
    let creates = 0;
    server.use(
      http.post(GENE_SETS, () => {
        creates += 1;
        if (creates === 1) {
          return HttpResponse.json({ detail: "gene set save failed" }, { status: 500 });
        }
        return new Promise<never>(() => {});
      }),
    );
    render(<GeneSearchSidebar />, { wrapper: appQueryClientWrapper() });

    search("kinase");
    await createFromSelection("PF3D7_0100100");
    expect(await screen.findByText("gene set save failed")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(
      await screen.findByRole("checkbox", { name: "Select PF3D7_0100100" }),
    ).toBeChecked();
    expect(screen.queryByText("gene set save failed")).toBe(null);
    expect(creates).toBe(2);
  });
});
