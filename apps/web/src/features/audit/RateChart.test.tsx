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
import { RateChart } from "./RateChart";

const flush = () => new Promise<void>((resolve) => queueMicrotask(resolve));

describe("RateChart", () => {
  it("states every rate and interval in its label and draws them", async () => {
    render(<RateChart rates={SAMPLE_RUN.rates} checks={SAMPLE_WORDS.checks} />);
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      "Error rate with its 95% interval: Plasmodium falciparum Dd2: Gene length against orthologs 33% (6% to 79%), 1 of 3; Plasmodium falciparum NF54: Pseudogene calls on intact genes 100% (21% to 100%), 1 of 1",
    );
    await flush();
    expect(setOption).toHaveBeenCalledTimes(1);
  });

  it("draws nothing when no rate has a judged finding", () => {
    const { container } = render(<RateChart rates={[]} checks={SAMPLE_WORDS.checks} />);
    expect(container).toBeEmptyDOMElement();
  });
});
