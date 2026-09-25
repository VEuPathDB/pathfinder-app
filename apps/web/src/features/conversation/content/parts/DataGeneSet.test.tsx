/**
 * @vitest-environment jsdom
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { createTestWrapper } from "@/lib/query/testing";

import { server } from "../../../../../vitest.msw-setup";
import { DataGeneSet } from "./DataGeneSet";

const GENE_SETS = "http://localhost:3000/api/v1/gene-sets";
const GENE_SET_ID = "5b0c2f5e-3a51-4f7e-9d0c-0f4d3a1f2b61";
const VDI_ID = "soV5JEQEcF00p";

const PART = {
  geneSetId: GENE_SET_ID,
  name: "Erythrocytic Transcripts",
  geneCount: 3420,
  siteId: "plasmodb",
};

function listed(overrides: Record<string, unknown> = {}) {
  return {
    id: GENE_SET_ID,
    name: "Erythrocytic Transcripts",
    siteId: "plasmodb",
    geneIds: ["PF3D7_1133400", "PF3D7_0709000"],
    source: "strategy",
    geneCount: 3420,
    membershipDigest: "0000000000000d5c",
    createdAt: "2026-09-05T00:00:00Z",
    stepCount: 2,
    vdiId: null,
    ...overrides,
  };
}

/** Serves the list and records every DELETE the figure sends; `refusal` is the
 * status the api answers a delete with instead. */
function serve(sets: object[], refusal: number | null = null): string[] {
  const deleted: string[] = [];
  let current = sets;
  server.use(
    http.get(GENE_SETS, () => HttpResponse.json(current)),
    http.delete(`${GENE_SETS}/:id`, ({ params }) => {
      if (refusal !== null) {
        return HttpResponse.json(
          { title: "Conflict", status: refusal, detail: "The set is in use" },
          { status: refusal },
        );
      }
      deleted.push(String(params["id"]));
      current = [];
      return HttpResponse.json({ ok: true });
    }),
  );
  return deleted;
}

function renderFigure() {
  const { Wrapper } = createTestWrapper();
  return render(<DataGeneSet data={PART} />, { wrapper: Wrapper });
}

describe("DataGeneSet", () => {
  it("titles the figure with the gene set name", () => {
    serve([listed()]);
    renderFigure();
    expect(screen.getByText("Erythrocytic Transcripts").tagName).toBe("FIGCAPTION");
    expect(screen.getByTestId("data-gene-set")).toHaveTextContent("Gene set created");
  });

  it("captions the figure with the gene count and the site's short name", () => {
    serve([listed()]);
    renderFigure();
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "3,420 genes on PlasmoDB",
    );
  });

  it("draws no divider, no card and no outer margin", () => {
    serve([listed()]);
    renderFigure();
    expect(screen.getByTestId("figure").className).toBe("");
    expect(screen.getByTestId("data-gene-set").className).not.toMatch(
      /\bborder\b|\brounded-md\b|\bbg-card\b/,
    );
  });

  it("offers publish and delete for a set the researcher still holds", async () => {
    serve([listed()]);
    renderFigure();

    expect(
      await screen.findByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete gene set" })).toBeInTheDocument();
  });

  it("asks before it deletes, and a cancel deletes nothing", async () => {
    const user = userEvent.setup();
    const deleted = serve([listed()]);
    renderFigure();

    await user.click(await screen.findByRole("button", { name: "Delete gene set" }));
    expect(
      screen.getByRole("alertdialog", { name: "Delete Erythrocytic Transcripts?" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(deleted).toEqual([]);
    expect(screen.getByTestId("data-gene-set")).toHaveTextContent("Gene set created");
  });

  it("says the set was deleted and offers no actions after a confirmed delete", async () => {
    const user = userEvent.setup();
    const deleted = serve([listed()]);
    renderFigure();

    await user.click(await screen.findByRole("button", { name: "Delete gene set" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(screen.getByTestId("data-gene-set")).toHaveTextContent("Gene set deleted");
    });
    expect(deleted).toEqual([GENE_SET_ID]);
    expect(screen.queryByRole("button", { name: "Delete gene set" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    ).toBeNull();
  });

  it("reads a set that is no longer on the researcher's list as deleted", async () => {
    serve([listed({ id: "another-set" })]);
    renderFigure();

    await waitFor(() => {
      expect(screen.getByTestId("data-gene-set")).toHaveTextContent("Gene set deleted");
    });
    expect(screen.queryByRole("button", { name: "Delete gene set" })).toBeNull();
  });

  it("keeps the actions and says why when the api refuses the delete", async () => {
    const user = userEvent.setup();
    serve([listed()], 409);
    renderFigure();

    await user.click(await screen.findByRole("button", { name: "Delete gene set" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("The set is in use")).toBeInTheDocument();
    expect(screen.getByTestId("data-gene-set")).toHaveTextContent("Gene set created");
    expect(screen.getByRole("button", { name: "Delete gene set" })).toBeInTheDocument();
  });

  it("reads the dataset of a set already published instead of offering to publish", async () => {
    serve([listed({ vdiId: VDI_ID })]);
    server.use(
      http.get(`${GENE_SETS}/${GENE_SET_ID}/vdi-publication`, () =>
        HttpResponse.json({
          vdiId: VDI_ID,
          datasetUrl: `https://plasmodb.org/plasmo/app/workspace/datasets/${VDI_ID}`,
          siteId: "plasmodb",
          upload: "success",
          importStatus: "complete",
          installedTargets: ["PlasmoDB"],
          installed: true,
          isTerminal: true,
        }),
      ),
    );
    renderFigure();

    expect(await screen.findByText("Installed on PlasmoDB")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    ).toBeNull();
  });
});
