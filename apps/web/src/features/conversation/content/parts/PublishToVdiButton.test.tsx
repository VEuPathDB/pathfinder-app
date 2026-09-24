/**
 * @vitest-environment jsdom
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { GeneSet, VdiPublicationStatus } from "@pathfinder/shared";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTestWrapper } from "@/lib/query/testing";

const mockPublish = vi.hoisted(() => vi.fn());
const mockGetStatus = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/geneSets", () => ({
  publishGeneSetToVdi: mockPublish,
  getGeneSetVdiPublication: mockGetStatus,
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const { PublishToVdiButton } = await import("./PublishToVdiButton");

const VDI_ID = "soV5JEQEcF00p";
const DATASET_URL = `https://plasmodb.org/plasmo/app/workspace/datasets/${VDI_ID}`;

function geneSet(overrides: Partial<GeneSet> = {}): GeneSet {
  return {
    id: "gs-1",
    name: "Kinases with a signal peptide",
    siteId: "plasmodb",
    geneIds: ["PF3D7_1133400", "PF3D7_0709000"],
    source: "strategy",
    geneCount: 2,
    membershipDigest: "0000000000000010",
    createdAt: "2026-09-05T00:00:00Z",
    stepCount: 1,
    ...overrides,
  };
}

function status(overrides: Partial<VdiPublicationStatus> = {}): VdiPublicationStatus {
  return {
    vdiId: VDI_ID,
    datasetUrl: DATASET_URL,
    siteId: "plasmodb",
    upload: "success",
    importStatus: "complete",
    installedTargets: ["PlasmoDB"],
    installed: true,
    isTerminal: true,
    ...overrides,
  };
}

function renderButton(set: GeneSet) {
  const { Wrapper } = createTestWrapper();
  return render(<PublishToVdiButton geneSet={set} />, { wrapper: Wrapper });
}

describe("PublishToVdiButton", () => {
  beforeEach(() => {
    mockPublish.mockReset();
    mockGetStatus.mockReset();
  });

  it("starts idle, offering the publish action and calling nothing", () => {
    renderButton(geneSet());

    expect(
      screen.getByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Visibility")).toBeNull();
    expect(mockPublish).not.toHaveBeenCalled();
  });

  it("refuses to offer the action for a set with no genes", () => {
    renderButton(geneSet({ geneIds: [], geneCount: 0 }));

    const button = screen.getByRole<HTMLButtonElement>("button", {
      name: /Publish to VEuPathDB workspace/,
    });
    expect(button.disabled).toBe(true);
  });

  it("asks for a visibility and a confirmation before it publishes", async () => {
    const user = userEvent.setup();
    renderButton(geneSet());

    await user.click(
      screen.getByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    );

    expect(screen.getByLabelText<HTMLSelectElement>("Visibility").value).toBe(
      "private",
    );
    expect(screen.getByRole("button", { name: "Confirm publish" })).toBeTruthy();
    expect(mockPublish).not.toHaveBeenCalled();
  });

  it("cancelling returns to idle without publishing", async () => {
    const user = userEvent.setup();
    renderButton(geneSet());

    await user.click(
      screen.getByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Visibility")).toBeNull();
    expect(mockPublish).not.toHaveBeenCalled();
  });

  it("sends the chosen visibility and the set name, then shows the dataset", async () => {
    const user = userEvent.setup();
    mockPublish.mockResolvedValue({
      vdiId: VDI_ID,
      datasetUrl: DATASET_URL,
      siteId: "plasmodb",
      geneCount: 2,
    });
    mockGetStatus.mockResolvedValue(status());
    renderButton(geneSet());

    await user.click(
      screen.getByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    );
    await user.selectOptions(screen.getByLabelText("Visibility"), "public");
    await user.click(screen.getByRole("button", { name: "Confirm publish" }));

    await waitFor(() => {
      expect(screen.getByText("Installed on PlasmoDB")).toBeTruthy();
    });
    expect(mockPublish).toHaveBeenCalledWith("gs-1", {
      name: "Kinases with a signal peptide",
      visibility: "public",
    });
    expect(
      screen.getByRole<HTMLAnchorElement>("link", { name: /Open dataset/ }).href,
    ).toBe(DATASET_URL);
  });

  it("a refused publish shows the reason and offers the action again", async () => {
    const user = userEvent.setup();
    mockPublish.mockRejectedValue(new Error("PlasmoDB refused the upload"));
    renderButton(geneSet());

    await user.click(
      screen.getByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    );
    await user.click(screen.getByRole("button", { name: "Confirm publish" }));

    await waitFor(() => {
      expect(screen.getByText("PlasmoDB refused the upload")).toBeTruthy();
    });
    expect(
      screen.getByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    ).toBeTruthy();
  });

  it("a set that already carries a dataset reads its status instead", async () => {
    mockGetStatus.mockResolvedValue(
      status({ installed: false, isTerminal: false, importStatus: "queued" }),
    );
    renderButton(geneSet({ vdiId: VDI_ID }));

    await waitFor(() => {
      expect(screen.getByText("Upload success, import queued")).toBeTruthy();
    });
    expect(mockGetStatus).toHaveBeenCalledWith("gs-1");
    expect(
      screen.queryByRole("button", { name: /Publish to VEuPathDB workspace/ }),
    ).toBeNull();
  });

  it("a site that could not install the dataset says so", async () => {
    mockGetStatus.mockResolvedValue(
      status({ installed: false, isTerminal: true, installedTargets: [] }),
    );
    renderButton(geneSet({ vdiId: VDI_ID }));

    await waitFor(() => {
      expect(screen.getByText("The site could not install this dataset")).toBeTruthy();
    });
  });
});
