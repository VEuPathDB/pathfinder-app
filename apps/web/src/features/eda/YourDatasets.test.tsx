/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { EdaOwnDatasetResponse } from "@pathfinder/shared/generated/types/EdaOwnDatasetResponse";

import { server } from "../../../vitest.msw-setup";

import { YourDatasets } from "./YourDatasets";

const DATASETS = "http://localhost:3000/api/v1/eda/datasets";
const UPLOAD_URL = "https://plasmodb.org/plasmo/app/workspace/datasets";

function dataset(
  vdiId: string,
  state: EdaOwnDatasetResponse["state"],
  message: string | null = null,
): EdaOwnDatasetResponse {
  return {
    vdiId,
    name: `Upload ${vdiId}`,
    created: "2026-09-24T12:02:05Z",
    state,
    message,
    datasetId: state === "installed" ? `EDAUD_${vdiId}` : null,
    canSubset: state === "installed",
    canExportRows: state === "installed",
  };
}

function serve(datasets: EdaOwnDatasetResponse[]) {
  server.use(
    http.get(DATASETS, () => HttpResponse.json({ datasets, uploadUrl: UPLOAD_URL })),
  );
}

describe("YourDatasets", () => {
  it("links the site's own page for uploads, in a new tab", async () => {
    serve([]);
    render(<YourDatasets siteId="plasmodb" onPick={vi.fn()} />);

    const link = await screen.findByRole("link", { name: "Upload on VEuPathDB" });
    expect(link).toHaveAttribute("href", UPLOAD_URL);
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText("No datasets of yours on PlasmoDB.")).toBeInTheDocument();
  });

  it("lists an upload whose creation time carries the site's offset", async () => {
    serve([
      {
        ...dataset("lhZ5ptRgo014J", "installed"),
        name: "pathfinder-uat-deseq",
        created: "2026-09-29T09:52:08.771807-04:00",
      },
    ]);
    render(<YourDatasets siteId="plasmodb" onPick={vi.fn()} />);

    const row = await screen.findByTestId("eda-own-dataset-lhZ5ptRgo014J");
    expect(row).toHaveTextContent("pathfinder-uat-deseqYour upload");
    expect(screen.getByRole("link", { name: "Upload on VEuPathDB" })).toHaveAttribute(
      "href",
      UPLOAD_URL,
    );
  });

  it("opens an installed upload by its study id", async () => {
    serve([dataset("4xZ5Q5pV1s4IM", "installed")]);
    const onPick = vi.fn();
    render(<YourDatasets siteId="plasmodb" onPick={onPick} />);

    const row = await screen.findByTestId("eda-own-dataset-4xZ5Q5pV1s4IM");
    await userEvent.click(
      within(row).getByRole("button", { name: /Upload 4xZ5Q5pV1s4IM/ }),
    );

    expect(onPick).toHaveBeenCalledWith("EDAUD_4xZ5Q5pV1s4IM");
  });

  it("offers no way to open an upload that is installing, waiting or failed", async () => {
    serve([
      dataset("wtZ5dUpN8J0IE", "installing"),
      dataset("ctZ5MhpEs50I5", "waiting", "Installed; the study is not visible yet."),
      dataset("MoZ5BBpM8U0IM", "failed", "Every count must be a whole number."),
    ]);
    render(<YourDatasets siteId="plasmodb" onPick={vi.fn()} />);

    const rows = await screen.findAllByTestId(/^eda-own-dataset-/);
    expect(rows.map((row) => row.textContent)).toEqual([
      "Upload wtZ5dUpN8J0IEInstalling on VEuPathDB",
      "Upload ctZ5MhpEs50I5Installed; the study is not visible yet.",
      "Upload MoZ5BBpM8U0IMEvery count must be a whole number.",
    ]);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
