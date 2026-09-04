/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { EmptyState } from "@/components/ui/empty-state";

describe("EmptyState", () => {
  it("renders the heading alone when nothing else is given", () => {
    render(<EmptyState heading="No gene sets" />);
    expect(screen.getByRole("heading", { name: "No gene sets" })).toBeInTheDocument();
  });

  it("renders the icon, description and action when given", () => {
    render(
      <EmptyState
        icon={<span data-testid="icon" />}
        heading="No gene sets"
        description="Save a search to start."
        action={<button type="button">Add</button>}
      />,
    );
    expect(screen.getByTestId("icon")).toBeInTheDocument();
    expect(screen.getByText("Save a search to start.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("omits the description when it is empty", () => {
    render(<EmptyState heading="No gene sets" description="" />);
    expect(document.querySelectorAll("p")).toHaveLength(0);
  });
});
