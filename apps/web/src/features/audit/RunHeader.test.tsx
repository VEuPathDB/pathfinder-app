/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { RunHeader } from "./RunHeader";

describe("RunHeader", () => {
  it("states what the audit examines, on which release, and the requests it made", () => {
    render(<RunHeader view={SAMPLE_RUN} words={SAMPLE_WORDS} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Audit of Plasmodium falciparum NF54, Plasmodium falciparum Dd2 and 3 gene targets on PlasmoDB",
    );
    expect(screen.getByText("Release 71")).toBeInTheDocument();
    const storeReads = SAMPLE_RUN.storeReads;
    const requests = screen.getByRole("list", {
      name: `Site requests: 21; genome-store reads: ${String(storeReads)}`,
    });
    expect(
      within(requests)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "Read the genomes: 4 site requests, 0 genome-store reads",
      "Find candidates: 2 site requests, 0 genome-store reads",
      `Check candidates in the DNA: 9 site requests, ${String(storeReads)} genome-store reads`,
      "Weigh against relatives and gene records: 6 site requests, 0 genome-store reads",
    ]);
    expect(
      screen.getByRole("link", {
        name: "Open the conversation that started this audit",
      }),
    ).toHaveAttribute("href", "/conversation/00000000-0000-4000-8000-000000000002");
  });

  it("states the genes it examined, its days and its checks", () => {
    render(<RunHeader view={SAMPLE_RUN} words={SAMPLE_WORDS} />);
    expect(screen.getByText("Genes examined").nextElementSibling).toHaveTextContent(
      /^2$/,
    );
    expect(screen.getByText("Started").nextElementSibling).toHaveTextContent(
      "Oct 22, 2026",
    );
    expect(screen.getByText("Finished").nextElementSibling).toHaveTextContent(
      "Oct 22, 2026",
    );
    expect(screen.getByText("Checks").nextElementSibling).toHaveTextContent(
      "Gene length against orthologs, Exon structure against RNA-seq, Organelle genes at the circular join, Pseudogene calls on intact genes and Strain model against its reference",
    );
  });

  it("lists each genome with its role, its read status and the site's reference-strain mark", () => {
    render(<RunHeader view={SAMPLE_RUN} words={SAMPLE_WORDS} />);
    expect(screen.getByRole("table", { name: "Genomes" })).toBeInTheDocument();
    const row = screen.getByRole("row", { name: /Plasmodium falciparum 3D7/ });
    expect(row).toHaveTextContent("Compared against");
    expect(row).toHaveTextContent("Read");
    expect(row).toHaveTextContent("Reference strain");
    expect(screen.getByRole("row", { name: /falciparum NF54/ })).not.toHaveTextContent(
      "Reference strain",
    );
  });

  it("offers no conversation or release a run does not hold", () => {
    render(
      <RunHeader
        view={{
          ...SAMPLE_RUN,
          run: { ...SAMPLE_RUN.run, conversationId: null, release: null },
        }}
        words={SAMPLE_WORDS}
      />,
    );
    expect(screen.queryByRole("link")).toBe(null);
    expect(screen.queryByText(/^Release/)).toBe(null);
  });
});
