// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { purgeUserDataEndpoint } from "@pathfinder/shared/generated/hooks/usePurgeUserDataEndpoint";
import type { PurgeCounts } from "@pathfinder/shared/generated/types/PurgeCounts";

import { DataSettings } from "./DataSettings";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@pathfinder/shared/generated/hooks/usePurgeUserDataEndpoint", () => ({
  purgeUserDataEndpoint: vi.fn(),
}));
vi.mock("@pathfinder/shared/generated/hooks/useListStrategies", () => ({
  listStrategies: vi.fn(() => Promise.resolve([])),
}));
vi.mock("@pathfinder/shared/generated/hooks/useDeleteStrategy", () => ({
  deleteStrategy: vi.fn(() => Promise.resolve({})),
}));

const mockPurge = vi.mocked(purgeUserDataEndpoint);
const mockSuccess = vi.mocked(toast.success);
const mockError = vi.mocked(toast.error);

function counts(over: Partial<PurgeCounts> = {}): PurgeCounts {
  return {
    strategies: 0,
    wdkStrategies: 0,
    wdkStrategiesKept: 0,
    memories: 0,
    geneSets: 0,
    experiments: 0,
    controlSets: 0,
    stagedEvalCases: 0,
    ...over,
  };
}

async function clearAllWithWdk(deleted: PurgeCounts): Promise<void> {
  mockPurge.mockResolvedValue({ ok: true, deleted });
  openWdkConfirmation();
  fireEvent.change(screen.getByPlaceholderText("delete my data"), {
    target: { value: "delete my data" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

function openWdkConfirmation(): void {
  render(<DataSettings siteId="plasmodb" />);
  fireEvent.click(screen.getByRole("button", { name: "Clear ALL + VEuPathDB" }));
}

describe("DataSettings", () => {
  it("states the VEuPathDB blast radius the purge really has", () => {
    openWdkConfirmation();

    expect(
      screen.getByText(
        "This permanently deletes the strategies PathFinder created in your VEuPathDB account, on every site. Strategies you made in VEuPathDB yourself are kept.",
      ),
    ).toBeVisible();
  });

  it("describes the row as deleting only the strategies PathFinder created", () => {
    render(<DataSettings siteId="plasmodb" />);

    expect(screen.getByTestId("wdk-purge-description")).toHaveTextContent(
      "Delete everything locally, memories and the investigations still waiting for review included, and the strategies PathFinder created in VEuPathDB. A conversation or a run whose strategy the site keeps is kept too, so you can try again. Your monthly spend counter and exports stay. This cannot be undone.",
    );
  });

  it("says what clearing strategies does to the conversations on this site", () => {
    render(<DataSettings siteId="plasmodb" />);

    expect(
      screen.getByText(
        "Remove every conversation for PlasmoDB from PathFinder. A conversation linked to a VEuPathDB strategy moves to Recently deleted instead, and the strategy itself stays. Gene sets, runs and control sets are untouched.",
      ),
    ).toBeVisible();
  });

  it("names everything clearing the site data takes, and what it only hides", () => {
    render(<DataSettings siteId="plasmodb" />);

    expect(
      screen.getByText(
        "Delete the gene sets, runs and control sets for PlasmoDB, and move every conversation on it to Recently deleted. The investigations from PlasmoDB still waiting for review go with them. A conversation in Recently deleted can be restored from the sidebar. VEuPathDB strategies and your memories stay.",
      ),
    ).toBeVisible();
  });

  it("says the local purge takes the memories and names what stays", () => {
    render(<DataSettings siteId="plasmodb" />);

    expect(
      screen.getByText(
        "Delete the gene sets, runs and control sets on every site, and your memories with them. The investigations still waiting for review go too. Every conversation moves to Recently deleted, and can be restored from the sidebar. VEuPathDB strategies are kept but hidden from sync. Your monthly spend counter and exports stay.",
      ),
    ).toBeVisible();
  });

  it("holds Confirm shut until the phrase is typed", () => {
    openWdkConfirmation();

    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("delete my data"), {
      target: { value: "delete my data" },
    });

    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("reports a purge that finished everywhere", async () => {
    await clearAllWithWdk(counts({ wdkStrategies: 3, memories: 12 }));

    await waitFor(() => {
      expect(mockSuccess.mock.calls).toEqual([
        [
          "Data cleared",
          {
            description: "VEuPathDB strategies deleted: 3. Memories deleted: 12.",
          },
        ],
      ]);
    });
    expect(mockError).not.toHaveBeenCalled();
  });

  it("reports the strategies it could not delete and that their conversations were kept", async () => {
    await clearAllWithWdk(
      counts({ wdkStrategies: 1, wdkStrategiesKept: 2, memories: 12 }),
    );

    await waitFor(() => {
      expect(mockError.mock.calls).toEqual([
        [
          "Not everything was deleted",
          {
            description:
              "VEuPathDB strategies deleted: 1. Could not delete: 2. The conversations and runs that used them were kept, so you can try again. Memories deleted: 12.",
          },
        ],
      ]);
    });
    expect(mockSuccess).not.toHaveBeenCalled();
  });

  it("reports a purge that had nothing to delete on VEuPathDB", async () => {
    await clearAllWithWdk(counts());

    await waitFor(() => {
      expect(mockSuccess.mock.calls).toEqual([
        [
          "Data cleared",
          {
            description: "VEuPathDB strategies deleted: 0. Memories deleted: 0.",
          },
        ],
      ]);
    });
  });
});
