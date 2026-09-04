/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ApprovalCard } from "./ApprovalCard";

const INPUT = { wdkStepId: 132, searchName: "GenesByText" };

function draw(patch: {
  showRaw?: boolean;
  decision?: "pending" | "approved" | "denied";
  onApprove?: () => void;
  onDeny?: () => void;
}) {
  return render(
    <ApprovalCard
      prompt="Optimize parameters needs your approval before it runs."
      input={INPUT}
      showRaw={patch.showRaw ?? false}
      onApprove={patch.onApprove ?? (() => {})}
      onDeny={patch.onDeny ?? (() => {})}
      decision={patch.decision ?? "pending"}
    />,
  );
}

describe("ApprovalCard", () => {
  it("asks exactly the question its caller wrote", () => {
    draw({});
    expect(screen.getByTestId("approval-card-title")).toHaveTextContent(
      "Optimize parameters needs your approval before it runs.",
    );
  });

  it("separates itself from the trace above with the one paragraph gap", () => {
    draw({});
    const tokens = screen.getByTestId("approval-card").className.split(/\s+/);
    expect(tokens).toContain("mt-3");
    expect(tokens.filter((token) => token.startsWith("my-"))).toEqual([]);
  });

  it("offers both answers and keeps the controls testid the thread carried", () => {
    draw({});
    const controls = screen.getByTestId("tool-approval-controls");
    expect(controls).toContainElement(screen.getByTestId("tool-approval-approve"));
    expect(controls).toContainElement(screen.getByTestId("tool-approval-deny"));
    expect(screen.getByTestId("tool-approval-approve")).toHaveTextContent("Approve");
    expect(screen.getByTestId("tool-approval-deny")).toHaveTextContent("Deny");
  });

  it("reports each answer to its own handler", () => {
    const onApprove = vi.fn();
    const onDeny = vi.fn();
    draw({ onApprove, onDeny });
    fireEvent.click(screen.getByTestId("tool-approval-approve"));
    fireEvent.click(screen.getByTestId("tool-approval-deny"));
    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onDeny).toHaveBeenCalledTimes(1);
  });

  it("hides the call's input while the dev flag is off", () => {
    const view = draw({ showRaw: false });
    expect(view.container.textContent).not.toContain("wdkStepId");
    expect(view.container.textContent).not.toContain("{");
  });

  it("shows the call's input while the dev flag is on", () => {
    const view = draw({ showRaw: true });
    expect(view.container.textContent).toContain("wdkStepId");
    expect(view.container.textContent).toContain("GenesByText");
  });

  it("replaces the question with the answer once it is given", () => {
    const approved = draw({ decision: "approved" });
    expect(approved.getByTestId("tool-approval-decision")).toHaveTextContent(
      "Approved",
    );
    expect(approved.queryByTestId("tool-approval-approve")).toBeNull();
    expect(approved.queryByTestId("approval-card")).toBeNull();
    approved.unmount();

    const denied = draw({ decision: "denied" });
    expect(denied.getByTestId("tool-approval-decision")).toHaveTextContent("Denied");
  });

  it("is the one place in the thread that still draws a bordered box", () => {
    draw({});
    expect(screen.getByTestId("approval-card")).toHaveClass(
      "rounded-md",
      "border",
      "border-warning/40",
      "bg-warning/10",
      "p-3",
    );
  });
});
