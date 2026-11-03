/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const { setOption } = vi.hoisted(() => ({ setOption: vi.fn() }));
vi.mock("@/lib/components/charts/echartsRegistry", () => ({
  initChart: () => ({
    setOption,
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: () => false,
  }),
}));

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { RateHeatMap } from "./RateHeatMap";

const flush = () => new Promise<void>((resolve) => queueMicrotask(resolve));

describe("RateHeatMap", () => {
  it("states each cell's rate, interval and errors in its label and draws them", async () => {
    render(<RateHeatMap view={SAMPLE_RUN} words={SAMPLE_WORDS} />);
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      "Error rate by screened genome and check: Plasmodium falciparum Dd2, Gene length against orthologs 33% (6% to 79%), Model too short; Plasmodium falciparum NF54, Pseudogene calls on intact genes 100% (21% to 100%), Intact gene called a pseudogene",
    );
    await flush();
    expect(setOption).toHaveBeenCalledTimes(1);
  });

  it("draws nothing for a run with no rate", () => {
    const { container } = render(
      <RateHeatMap view={{ ...SAMPLE_RUN, rates: [] }} words={SAMPLE_WORDS} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
