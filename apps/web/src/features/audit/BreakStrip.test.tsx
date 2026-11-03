/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { SELK_STOPS_AT_SEC } from "./__fixtures__/recordedAudits";
import {
  organelleConfirmation,
  pseudogeneConfirmation,
} from "./__fixtures__/sampleConfirmations";
import { BreakStrip } from "./BreakStrip";

describe("BreakStrip", () => {
  it("draws a selenoprotein end as the residues the genome and the reference hold", () => {
    const { container } = render(
      <BreakStrip
        confirmation={{ check: "selenoprotein_end", result: SELK_STOPS_AT_SEC }}
      />,
    );
    expect(
      screen.getByRole("img", {
        name: "Genome after the model's end: stop, G, stop. Reference from its selenocysteine: selenocysteine, G.",
      }),
    ).toBeInTheDocument();
    expect(
      [...container.querySelectorAll('[data-part="residue"]')].map(
        (cell) => cell.textContent,
      ),
    ).toEqual(["*", "G", "*", "U", "G"]);
  });

  it("states a pseudogene call's premature stops by residue", () => {
    const stored = pseudogeneConfirmation();
    render(
      <BreakStrip
        confirmation={{
          ...stored,
          result: { ...stored.result, prematureStops: [163, 200] },
        }}
      />,
    );
    expect(
      screen.getByText("Stops inside the rebuilt protein at residues 163 and 200"),
    ).toBeInTheDocument();
  });

  it("says when the list of stops holds only the first ones", () => {
    const stored = pseudogeneConfirmation();
    render(
      <BreakStrip
        confirmation={{
          ...stored,
          result: {
            ...stored.result,
            prematureStops: [163],
            prematureStopsTruncated: true,
          },
        }}
      />,
    );
    expect(
      screen.getByText("Stops inside the rebuilt protein at residue 163 (the first 1)"),
    ).toBeInTheDocument();
  });

  it("draws nothing for a pseudogene call with no stop", () => {
    const { container } = render(
      <BreakStrip confirmation={pseudogeneConfirmation()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("draws nothing for a check that stores no break", () => {
    const { container } = render(<BreakStrip confirmation={organelleConfirmation()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
