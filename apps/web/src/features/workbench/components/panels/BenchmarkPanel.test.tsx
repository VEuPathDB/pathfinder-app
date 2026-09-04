// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Experiment } from "@pathfinder/shared";
import type { BenchmarkStreamEvent } from "@/features/workbench/api/streaming";

const storeState: Record<string, unknown> = {
  activeSetId: "set-1",
  positiveControls: ["PF3D7_0709000"],
  negativeControls: [],
  expandedPanels: new Set(["benchmark"]),
  togglePanel: vi.fn(),
};

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector(storeState),
}));
vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ selectedSite: "plasmodb" }),
}));
vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({
    data: [
      {
        id: "set-1",
        siteId: "plasmodb",
        recordType: "transcript",
        searchName: "GenesByTaxon",
        parameters: {},
        name: "Kinases",
        geneIds: ["PF3D7_0100100"],
      },
    ],
  }),
}));

const createBenchmarkStream = vi.fn();
vi.mock("@/features/workbench/api", () => ({
  createBenchmarkStream: (...args: unknown[]) => createBenchmarkStream(...args),
}));

import { BenchmarkPanel } from "./BenchmarkPanel";

const CONTROL_SETS = [
  {
    label: "Stringent",
    positiveControls: ["PF3D7_0709000"],
    negativeControls: ["PF3D7_0930300"],
    isPrimary: true,
  },
  {
    label: "Lenient",
    positiveControls: ["PF3D7_1133400"],
    negativeControls: [],
    isPrimary: false,
  },
];

describe("BenchmarkPanel", () => {
  it("benchmarks the active strategy across the provided control sets", async () => {
    async function* stream(): AsyncGenerator<BenchmarkStreamEvent> {
      yield { type: "experiment_progress", data: { phase: "scoring" } };
      yield {
        type: "benchmark_complete",
        benchmarkId: "bench-1",
        experiments: [
          {
            id: "exp-stringent",
            config: { name: "Stringent" },
            status: "completed",
            metrics: { mcc: 0.71 },
          } as unknown as Experiment,
          {
            id: "exp-lenient",
            config: { name: "Lenient" },
            status: "completed",
            metrics: { mcc: 0.55 },
          } as unknown as Experiment,
        ],
      };
    }
    createBenchmarkStream.mockReturnValue(stream());
    render(<BenchmarkPanel />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: JSON.stringify(CONTROL_SETS) },
    });
    await userEvent.click(screen.getByText(/Run benchmark/i));

    await waitFor(() =>
      expect(screen.getByText(/2 experiments complete/i)).toBeInTheDocument(),
    );

    // The benchmark request carried the parsed control sets + real base config.
    const call = createBenchmarkStream.mock.calls[0] as [
      { positiveControls: string[]; searchName: string },
      typeof CONTROL_SETS,
    ];
    expect(call[1].map((c) => c.label)).toEqual(["Stringent", "Lenient"]);
    expect(call[1][0]?.positiveControls).toEqual(["PF3D7_0709000"]);
    expect(call[0].searchName).toBe("GenesByTaxon");
  });

  it("reports malformed control-set JSON instead of calling the backend", async () => {
    render(<BenchmarkPanel />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "{not json" } });
    await userEvent.click(screen.getByText(/Run benchmark/i));
    await waitFor(() => expect(screen.getByText(/malformed/i)).toBeInTheDocument());
    expect(createBenchmarkStream).not.toHaveBeenCalled();
  });

  it("renders nothing without an active gene set", () => {
    storeState["activeSetId"] = "missing";
    const { container } = render(<BenchmarkPanel />);
    expect(container).toBeEmptyDOMElement();
    storeState["activeSetId"] = "set-1";
  });
});
