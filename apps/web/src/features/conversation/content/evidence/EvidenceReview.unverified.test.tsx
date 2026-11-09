// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { EvidenceReview } from "./EvidenceReview";

afterEach(cleanup);

describe("EvidenceReview", () => {
  it("reads a requirement nothing compared as not verified, never as a failure", () => {
    render(
      <EvidenceReview
        review={{
          checks: [
            {
              kind: "count",
              subject: "at least 2 transmembrane domains",
              status: "unchecked",
              evidence: "no criterion links it to a parameter",
              requirement: "r1",
              whyUnchecked: "no_value_to_compare",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.queryByText(/Failed|Passed/)).not.toBeInTheDocument();
  });
});
