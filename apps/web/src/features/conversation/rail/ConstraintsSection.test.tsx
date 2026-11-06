// @vitest-environment jsdom
import { afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

afterEach(cleanup);

import { constraintKindEnum } from "@pathfinder/shared/generated/types/ConstraintKind";

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
    expect(screen.getByText("data type *")).toBeInTheDocument();
    expect(screen.getByText("substituted")).toBeInTheDocument();
    expect(screen.getByTestId("constraints-summary")).toHaveTextContent(
      "1 requirement is not met: data type.",
    );
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

  it("states in one line what is true of the requirements, with no counters", () => {
    render(
      <ConstraintsSection
        constraints={{
          blocking: false,
          unmetCount: 0,
          grounded: ["enzymes", "interfere with host proteins"].map((label) => ({
            constraint: {
              kind: "property" as const,
              requestedValue: label,
              label,
              source: "user_explicit" as const,
              hard: true,
            },
            status: "not_verified" as const,
            unverified: "no_step_states_it" as const,
          })),
        }}
      />,
    );
    expect(screen.getByTestId("constraints-summary")).toHaveTextContent(
      "2 requirements are not in any step: enzymes, interfere with host proteins.",
    );
    expect(screen.queryByText("blocking")).not.toBeInTheDocument();
    expect(screen.queryByText(/unmet/)).not.toBeInTheDocument();
  });

  it("shows a row for a requirement of every kind", () => {
    const kinds = Object.values(constraintKindEnum);
    render(
      <ConstraintsSection
        constraints={{
          blocking: false,
          unmetCount: 0,
          grounded: kinds.map((kind) => ({
            constraint: {
              kind,
              requestedValue: `value of ${kind}`,
              label: `label of ${kind}`,
              source: "user_explicit",
              hard: true,
            },
            status: "not_verified",
            unverified: "untyped",
          })),
        }}
      />,
    );
    expect(
      kinds.map(
        (kind) => screen.getByText(`requested value of ${kind} -> -`).textContent,
      ),
    ).toEqual(kinds.map((kind) => `requested value of ${kind} -> -`));
    expect(screen.getAllByText("not verified")).toHaveLength(kinds.length);
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
