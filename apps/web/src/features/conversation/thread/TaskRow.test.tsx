/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { TaskRow } from "./TaskRow";

const RUNNING = {
  label: "Run control tests",
  percent: 0.66,
  message: "Comparing controls",
  estimatedSeconds: 3,
  outcome: "running",
  error: null,
} as const;

describe("TaskRow", () => {
  it("reads the label, the percent and the estimate while the job runs", () => {
    render(<TaskRow {...RUNNING} />);
    const row = screen.getByTestId("task-row");
    expect(row).toHaveTextContent("Run control tests");
    expect(within(row).getByTestId("task-row-status")).toHaveTextContent("66%");
    expect(within(row).getByTestId("task-row-elapsed")).toHaveTextContent("~3 s");
    expect(row).toHaveTextContent("Comparing controls");
  });

  it("sets no outer margin, so the message container owns the rhythm", () => {
    render(<TaskRow {...RUNNING} />);
    expect(screen.getByTestId("task-row").className).toBe("");
  });

  it("drives the bar's fill from the percent", () => {
    render(<TaskRow {...RUNNING} />);
    expect(screen.getByTestId("progress-bar-fill").style.width).toBe("66%");
  });

  it("paints the bar with the theme's primary, never a hardcoded blue", () => {
    render(<TaskRow {...RUNNING} />);
    const fill = screen.getByTestId("progress-bar-fill");
    expect(fill).toHaveClass("bg-primary");
    expect(fill.getAttribute("class")).not.toContain("bg-blue-500");
  });

  it("reads Completed and keeps its bar once the job succeeds", () => {
    render(
      <TaskRow
        label="Run control tests"
        percent={1}
        message={null}
        estimatedSeconds={3}
        outcome="success"
        error={null}
      />,
    );
    const row = screen.getByTestId("task-row");
    expect(within(row).getByTestId("task-row-status")).toHaveTextContent("Completed");
    expect(within(row).getByTestId("data-task-progress")).toBeInTheDocument();
    expect(within(row).getByTestId("progress-bar-fill")).toHaveStyle({ width: "100%" });
    expect(within(row).queryByTestId("task-row-elapsed")).toBeNull();
  });

  it("reads Failed and prints the worker's error under the row", () => {
    render(
      <TaskRow
        label="Optimize parameters"
        percent={0.4}
        message={null}
        estimatedSeconds={null}
        outcome="failure"
        error="WDK rejected the search"
      />,
    );
    const row = screen.getByTestId("task-row");
    expect(within(row).getByTestId("task-row-status")).toHaveTextContent("Failed");
    expect(row).toHaveTextContent("WDK rejected the search");
  });

  it("shows no estimate when the started payload carried none", () => {
    render(
      <TaskRow
        label="Run control tests"
        percent={null}
        message={null}
        estimatedSeconds={null}
        outcome="running"
        error={null}
      />,
    );
    expect(screen.queryByTestId("task-row-elapsed")).toBeNull();
    expect(screen.getByTestId("task-row").textContent).toBe("Run control testsQueued");
  });

  it("reads Queued, not 0%, before the task reports any progress", () => {
    render(
      <TaskRow
        label="Run control tests"
        percent={null}
        message={null}
        estimatedSeconds={120}
        outcome="running"
        error={null}
      />,
    );
    expect(screen.getByTestId("task-row-status").textContent).toBe("Queued");
  });

  it("reads 0% once the task reports that it started at zero", () => {
    render(
      <TaskRow
        label="Run control tests"
        percent={0}
        message="Querying the step"
        estimatedSeconds={120}
        outcome="running"
        error={null}
      />,
    );
    expect(screen.getByTestId("task-row-status").textContent).toBe("0%");
  });

  it("shows the tool's own line in place of Completed", () => {
    render(
      <TaskRow
        label="Run control tests"
        percent={1}
        message={null}
        estimatedSeconds={null}
        outcome="success"
        error={null}
        summary="2 of 3 positive controls recovered"
      />,
    );
    expect(screen.getByTestId("task-row-status")).toHaveTextContent(
      "2 of 3 positive controls recovered",
    );
  });

  it("keeps Failed over a line a failed call left behind", () => {
    render(
      <TaskRow
        label="Run control tests"
        percent={1}
        message={null}
        estimatedSeconds={null}
        outcome="failure"
        error="WDK rejected the search"
        summary="2 of 3 positive controls recovered"
      />,
    );
    expect(screen.getByTestId("task-row-status")).toHaveTextContent("Failed");
  });

  it("points at no exhibit, because the exhibit reads under the row", () => {
    render(
      <TaskRow
        label="Run control tests"
        percent={1}
        message={null}
        estimatedSeconds={null}
        outcome="success"
        error={null}
      />,
    );
    const row = screen.getByTestId("task-row");
    expect(within(row).queryByRole("link")).toBeNull();
    expect(row).not.toHaveTextContent("see Table");
    expect(within(row).getByTestId("task-row-status")).toHaveTextContent("Completed");
  });

  it("carries no JSON, whatever the job reported", () => {
    const view = render(<TaskRow {...RUNNING} />);
    expect(view.container.textContent).not.toContain("{");
    expect(view.container.textContent).toContain("Run control tests");
  });
});
