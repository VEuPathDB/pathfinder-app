/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { TraceGroup } from "./TraceGroup";
import type { TraceGroupView, TraceRowView } from "./traceTypes";

function step(patch: Partial<TraceRowView>): TraceRowView {
  return {
    key: "call_delete_step",
    toolCallId: "call_delete_step",
    toolName: "delete_step",
    summary: "step s2 removed",
    status: "ok",
    input: { stepId: "s2" },
    output: null,
    errorText: null,
    ...patch,
  };
}

function group(patch: Partial<TraceGroupView>): TraceGroupView {
  return {
    key: "lead_call_recover",
    phase: "execution",
    rows: [step({})],
    tokens: 0,
    costUsd: "0",
    state: "completed",
    ...patch,
  };
}

function draw(patch: Partial<TraceGroupView>, showUsage = true) {
  return render(
    <TraceGroup
      group={group(patch)}
      bare={false}
      showRaw={false}
      showUsage={showUsage}
      nameFor={(name) => (name === "delete_step" ? "Delete step" : name)}
    />,
  );
}

describe("TraceGroup", () => {
  it("labels a recorded execution phase Build, through the shared label set", () => {
    draw({});
    expect(screen.getByTestId("trace-group-label")).toHaveTextContent("Build");
  });

  it("carries the sub-agent call testid the thread has always had", () => {
    const view = draw({});
    const call = view.getByTestId("data-sub-agent-call");
    expect(within(call).getByTestId("trace-group")).toBeInTheDocument();
    expect(within(call).getAllByTestId("trace-row")).toHaveLength(1);
  });

  it("prints the sub-agent's own tokens and cost beside its label", () => {
    const view = draw({ tokens: 12300, costUsd: "0.004" });
    expect(view.getByTestId("trace-group-usage")).toHaveTextContent("12.3K, $0.004");
  });

  it("reads Denied, not Error, for a step the user refused", () => {
    const view = draw({
      rows: [step({ status: "denied", summary: "Keep that step.", errorText: null })],
    });
    expect(view.getByTestId("trace-row-status")).toHaveClass("text-muted-foreground");
    expect(view.getByTestId("trace-row-summary")).toHaveTextContent("Keep that step.");
  });

  it("reads the failure text for a step that failed", () => {
    const view = draw({
      rows: [
        step({
          status: "error",
          summary: null,
          errorText: "step s2 has no parent",
        }),
      ],
    });
    expect(view.getByTestId("trace-row-status")).toHaveClass("text-destructive");
    expect(view.getByTestId("trace-row-summary")).toHaveTextContent(
      "step s2 has no parent",
    );
  });

  it("names every step it holds", () => {
    const view = draw({
      rows: [
        step({ key: "s1", toolCallId: "s1" }),
        step({ key: "s2", toolCallId: "s2" }),
      ],
    });
    expect(view.getAllByTestId("trace-row")).toHaveLength(2);
    expect(view.getAllByTestId("trace-row")[0]).toHaveTextContent("Delete step");
  });

  it("says Stopped for a dispatch the user's stop left open", () => {
    const view = draw({ state: "cancelled" });
    expect(view.getByTestId("trace-group-state")).toHaveTextContent("Stopped");
  });

  it("says Not finished for a dispatch that outlived its turn", () => {
    const view = draw({ state: "superseded" });
    expect(view.getByTestId("trace-group-state")).toHaveTextContent("Not finished");
  });

  it("says nothing beside a dispatch that is running or done", () => {
    const started = draw({ state: "started" });
    expect(started.queryByTestId("trace-group-state")).toBeNull();
    expect(started.getAllByTestId("trace-row")).toHaveLength(1);
    const done = draw({ state: "completed" });
    expect(done.queryByTestId("trace-group-state")).toBeNull();
  });

  it("reads a stopped call under a cancelled dispatch as Stopped", () => {
    const view = draw({
      state: "cancelled",
      rows: [step({ status: "stopped", summary: null })],
    });
    expect(view.getByTestId("trace-row-summary")).toHaveTextContent("Stopped");
  });

  it("reads a stopped call under a failed dispatch as Not finished", () => {
    const view = draw({
      state: "failed",
      rows: [step({ status: "stopped", summary: null })],
    });
    expect(view.getByTestId("trace-row-summary")).toHaveTextContent("Not finished");
  });

  it("keeps the line a stopped call had already written", () => {
    const view = draw({
      state: "cancelled",
      rows: [step({ status: "stopped", summary: "12 searches" })],
    });
    expect(view.getByTestId("trace-row-summary")).toHaveTextContent("12 searches");
  });

  it("drops the heading entirely for the Lead's own bare group", () => {
    const view = render(
      <TraceGroup
        group={group({ key: "lead", phase: "lead" })}
        bare
        showRaw={false}
        showUsage
        nameFor={(name) => name}
      />,
    );
    expect(view.queryByTestId("trace-group")).toBeNull();
    expect(view.queryByTestId("data-sub-agent-call")).toBeNull();
    expect(view.getAllByTestId("trace-row")).toHaveLength(1);
  });
});
