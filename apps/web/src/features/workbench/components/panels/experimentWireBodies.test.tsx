// @vitest-environment jsdom
/**
 * Every panel that runs an experiment posts a body the API accepts, and
 * belongs in this file. The schemas below are the API's own.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { queryOptions } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createBatchExperimentRequestSchema } from "@pathfinder/shared/generated/zod/createBatchExperimentRequestSchema";
import { createBenchmarkRequestSchema } from "@pathfinder/shared/generated/zod/createBenchmarkRequestSchema";
import { createExperimentRequestSchema } from "@pathfinder/shared/generated/zod/createExperimentRequestSchema";
import type { z } from "zod";

import {
  CONTROL_SETS,
  ORGANISM_SPECS,
  SEARCH_BACKED_SET,
  SITE_ORGANISMS,
} from "./__fixtures__/experimentPanels";

const env = { geneSet: SEARCH_BACKED_SET };
const posted: Array<{ url: string; body: unknown }> = [];
vi.mock("@/lib/sse/typedEventStream", () => ({
  streamTypedEvents: (url: string, opts: { body?: unknown }) => {
    posted.push({ url, body: opts.body });
    return (async function* () {})();
  },
}));

vi.mock("@/state/useWorkbenchStore", () => ({
  useWorkbenchStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      activeSetId: "set-1",
      positiveControls: ["PF3D7_0709000"],
      negativeControls: ["PF3D7_0930300"],
      setPositiveControls: vi.fn(),
      setNegativeControls: vi.fn(),
      setLastExperiment: vi.fn(),
      expandedPanels: new Set(["evaluate", "batch", "benchmark"]),
      togglePanel: vi.fn(),
    }),
}));
vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ selectedSite: "plasmodb" }),
}));
vi.mock("@/features/workbench/hooks/useGeneSetsQuery", () => ({
  useGeneSetsQuery: () => ({ data: [env.geneSet] }),
}));
vi.mock("@tanstack/react-query", async (importActual) => ({
  ...(await importActual<Record<string, unknown>>()),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));
vi.mock("../ControlSetQuickPick", () => ({
  ControlSetQuickPick: () => <div data-testid="control-quick-pick" />,
}));
vi.mock("../GeneChipInput", () => ({
  GeneChipInput: ({ label }: { label: string }) => <div>{label}</div>,
}));
vi.mock("../SaveControlSetForm", () => ({
  SaveControlSetForm: () => <div data-testid="save-control-set" />,
}));
vi.mock("@/lib/api/sites", () => ({
  paramSpecsOptions: () =>
    queryOptions({
      queryKey: ["param-specs", "GenesByRNASeq"] as const,
      queryFn: () => Promise.resolve(ORGANISM_SPECS),
    }),
}));
vi.mock("@pathfinder/shared/generated/hooks/useGetOrganisms", () => ({
  getOrganismsQueryOptions: () =>
    queryOptions({
      queryKey: ["organisms", "plasmodb"] as const,
      queryFn: () => Promise.resolve({ organisms: SITE_ORGANISMS }),
    }),
}));
vi.mock("../../api/controlSets", () => ({
  controlSetsOptions: () =>
    queryOptions({
      queryKey: ["control-sets", "plasmodb"] as const,
      queryFn: () => Promise.resolve(CONTROL_SETS),
    }),
}));

import { BatchPanel } from "./BatchPanel";
import { BenchmarkPanel } from "./BenchmarkPanel";
import { EvaluatePanel } from "./EvaluatePanel";

beforeEach(() => {
  posted.length = 0;
  env.geneSet = SEARCH_BACKED_SET;
});

function accepted(schema: z.ZodType<unknown>, body: unknown): string {
  const parsed = schema.safeParse(body);
  return parsed.success
    ? "accepted"
    : parsed.error.issues
        .map((issue) => `${issue.path.join(".")}: ${issue.message}`)
        .join("; ");
}

describe("the bodies the experiment panels post", () => {
  it("Evaluate posts a request the API accepts", async () => {
    render(<EvaluatePanel />);
    await userEvent.click(screen.getByText(/Run evaluation/i));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]?.url).toBe("/api/v1/experiments");
    expect(accepted(createExperimentRequestSchema, posted[0]?.body)).toBe("accepted");
  });

  it("Batch posts a request the API accepts", async () => {
    render(<BatchPanel />);
    await userEvent.click(await screen.findByText(/Filter by organism/i));
    await userEvent.click(screen.getByText("Plasmodium falciparum 3D7"));
    await userEvent.click(screen.getByText(/Run 1 experiments/i));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]?.url).toBe("/api/v1/experiments/batch");
    expect(accepted(createBatchExperimentRequestSchema, posted[0]?.body)).toBe(
      "accepted",
    );
  });

  it("Evaluate refuses a fold count the API would refuse, and posts nothing", async () => {
    render(<EvaluatePanel />);
    await userEvent.click(screen.getByLabelText(/Cross-validation/i));
    const folds = screen.getByRole("spinbutton");
    await userEvent.clear(folds);
    await userEvent.type(folds, "1");

    expect(screen.getByTestId("evaluate-folds-refusal")).toHaveTextContent(
      "Cross-validation needs between 2 and 10 folds.",
    );
    expect(screen.getByText(/Run evaluation/i).closest("button")).toBeDisabled();
    expect(posted).toHaveLength(0);
  });

  it("Batch names a run after a long set without exceeding the API's limit", async () => {
    env.geneSet = { ...SEARCH_BACKED_SET, name: "P".repeat(250) };
    render(<BatchPanel />);
    await userEvent.click(await screen.findByText(/Filter by organism/i));
    await userEvent.click(screen.getByText("Plasmodium falciparum 3D7"));
    await userEvent.click(screen.getByText(/Run 1 experiments/i));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(accepted(createBatchExperimentRequestSchema, posted[0]?.body)).toBe(
      "accepted",
    );
    const body = posted[0]?.body as { base: { name: string } };
    expect(body.base.name).toHaveLength(200);
    expect(body.base.name.endsWith("... (batch)")).toBe(true);
  });

  it("Benchmark posts a request the API accepts", async () => {
    render(<BenchmarkPanel />);
    await userEvent.click(await screen.findByText(/gametocyte surface/i));
    await userEvent.click(screen.getByText(/Run 1 control sets/i));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]?.url).toBe("/api/v1/experiments/benchmark");
    expect(accepted(createBenchmarkRequestSchema, posted[0]?.body)).toBe("accepted");
  });
});
