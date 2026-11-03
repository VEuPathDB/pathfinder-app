// @vitest-environment jsdom
import { afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

afterEach(cleanup);

import { ConstraintsSection } from "./ConstraintsSection";

describe("ConstraintsSection", () => {
  it("shows a warn pill for a substituted user-explicit constraint", () => {
    render(
      <ConstraintsSection
        constraints={{
          blocking: true,
          unmetCount: 1,
          grounded: [
            {
              constraint: {
                kind: "data_type",
                requestedValue: "RNA-Seq",
                label: "data type",
                source: "user_explicit",
                hard: true,
              },
              status: "substituted",
              realizedValue: "microarray",
              note: "RNA-Seq unavailable",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText(/data type/i)).toBeInTheDocument();
    expect(screen.getByText(/substituted/i)).toBeInTheDocument();
    expect(screen.getByText(/requested RNA-Seq -> microarray/i)).toBeInTheDocument();
  });

  it("shows a requirement nothing compared as not verified", () => {
    render(
      <ConstraintsSection
        constraints={{
          blocking: false,
          unmetCount: 0,
          grounded: [
            {
              constraint: {
                kind: "property",
                requestedValue: "secreted",
                label: "secreted",
                source: "user_explicit",
                hard: true,
              },
              status: "not_verified",
              unverified: "no_step_states_it",
              note: "no step of the strategy states it",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("not verified")).toBeInTheDocument();
    expect(screen.queryByText(/grounded/i)).not.toBeInTheDocument();
  });

  it("renders nothing notable when there are no constraints", () => {
    render(
      <ConstraintsSection
        constraints={{ blocking: false, unmetCount: 0, grounded: [] }}
      />,
    );
    expect(screen.getByText(/none/i)).toBeInTheDocument();
  });
});
