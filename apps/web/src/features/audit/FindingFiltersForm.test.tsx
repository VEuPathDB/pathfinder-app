/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { filtersFromSearch } from "./findingFilters";
import { FindingFilters } from "./FindingFiltersForm";

function optionsOf(label: string): (string | null)[] {
  return within(screen.getByLabelText(label))
    .getAllByRole("option")
    .map((option) => option.textContent);
}

describe("FindingFilters", () => {
  it("offers the run's own checks, genomes and errors, and starts a new filter at the first page", async () => {
    const onChange = vi.fn();
    const state = filtersFromSearch(new URLSearchParams("offset=50"));
    render(
      <FindingFilters
        view={SAMPLE_RUN}
        words={SAMPLE_WORDS}
        state={state}
        onChange={onChange}
      />,
    );
    expect(optionsOf("Error")).toEqual([
      "Any",
      "Intact gene called a pseudogene",
      "Model too short",
      "Organelle gene split at the circular join",
      "Exon missing from the model",
    ]);
    expect(optionsOf("Genome with the error")).toEqual([
      "Any",
      "Plasmodium cynomolgi strain M",
      "Plasmodium falciparum Dd2",
      "Plasmodium falciparum NF54",
    ]);
    expect(optionsOf("Screened genome")).toEqual([
      "Any",
      "Plasmodium cynomolgi strain B",
      "Plasmodium cynomolgi strain M",
      "Plasmodium falciparum Dd2",
      "Plasmodium falciparum NF54",
    ]);
    await userEvent.selectOptions(screen.getByLabelText("Source"), "target");
    expect(onChange).toHaveBeenCalledWith({ ...state, origin: "target", offset: 0 });
  });

  it("clears a filter with its first option", async () => {
    const onChange = vi.fn();
    const state = filtersFromSearch(new URLSearchParams("check=gene_length"));
    render(
      <FindingFilters
        view={SAMPLE_RUN}
        words={SAMPLE_WORDS}
        state={state}
        onChange={onChange}
      />,
    );
    expect(screen.getByLabelText("Check")).toHaveValue("gene_length");
    await userEvent.selectOptions(screen.getByLabelText("Check"), "");
    expect(onChange).toHaveBeenCalledWith({ ...state, check: null, offset: 0 });
  });

  it("leaves the error out on a page fixed to one error type", () => {
    render(
      <FindingFilters
        view={SAMPLE_RUN}
        words={SAMPLE_WORDS}
        state={filtersFromSearch(new URLSearchParams())}
        onChange={vi.fn()}
        errorFixed
      />,
    );
    expect(screen.queryByLabelText("Error")).toBe(null);
    expect(screen.getByLabelText("Certainty")).toBeInTheDocument();
  });
});
