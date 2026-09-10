/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { DataResearchSources } from "./DataResearchSources";

const SOURCES = {
  query: "plasmodium falciparum kinome",
  sources: [
    {
      id: "lit_000000000001",
      url: "https://doi.org/10.1126/science.1188191",
      title: "A Plant-Like Kinase in Plasmodium falciparum",
    },
    {
      id: "lit_000000000002",
      url: "https://doi.org/10.1038/nmicrobiol.2016.4",
      title: "",
    },
  ],
};

describe("DataResearchSources", () => {
  it("links one row per source, titled or by its url", () => {
    render(<DataResearchSources data={SOURCES} />);
    const card = screen.getByTestId("data-research-sources");
    const rows = within(card).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByRole("link")).toHaveAttribute(
      "href",
      "https://doi.org/10.1126/science.1188191",
    );
    expect(rows[0]).toHaveTextContent("A Plant-Like Kinase in Plasmodium falciparum");
    expect(rows[1]).toHaveTextContent("https://doi.org/10.1038/nmicrobiol.2016.4");
  });

  it("captions the figure with the count and the query", () => {
    render(<DataResearchSources data={SOURCES} />);
    expect(screen.getByText("Sources").tagName).toBe("FIGCAPTION");
    expect(screen.getByTestId("figure-caption").textContent).toBe(
      "2 sources for plasmodium falciparum kinome",
    );
  });

  it("renders nothing when the call cited nothing", () => {
    const { container } = render(
      <DataResearchSources data={{ query: "kinases", sources: [] }} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when the tool sent no sources at all", () => {
    const { container } = render(<DataResearchSources data={{ query: "kinases" }} />);
    expect(container.innerHTML).toBe("");
  });
});
