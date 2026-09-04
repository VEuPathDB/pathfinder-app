/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import {
  fireEvent,
  render,
  screen,
  within,
  type RenderResult,
} from "@testing-library/react";

import { Trace, type TraceRunView } from "./Trace";
import type { TraceGroupView, TraceRowView } from "./traceTypes";

function row(patch: Partial<TraceRowView>): TraceRowView {
  return {
    key: "call_1",
    toolCallId: "call_1",
    toolName: "set_criterion",
    summary: "c1 set to GenesByText",
    status: "ok",
    input: {},
    output: null,
    errorText: null,
    ...patch,
  };
}

function group(patch: Partial<TraceGroupView>): TraceGroupView {
  return {
    key: "lead",
    phase: "lead",
    rows: [row({})],
    tokens: 0,
    costUsd: "0",
    state: "completed",
    ...patch,
  };
}

function run(patch: Partial<TraceRunView>): TraceRunView {
  const groups = patch.groups ?? [group({})];
  return {
    groups,
    rowCount: groups.reduce((total, each) => total + each.rows.length, 0),
    running: false,
    ...patch,
  };
}

function element(view: TraceRunView, showUsage = false) {
  return (
    <Trace run={view} showRaw={false} showUsage={showUsage} nameFor={(name) => name} />
  );
}

function draw(view: TraceRunView, showUsage = false) {
  return render(element(view, showUsage));
}

/** The collapsing grid, which carries no testid of its own. */
function rowsBox(view: RenderResult): HTMLElement {
  const box = view.getByTestId("turn-trace").querySelector("div.grid");
  if (!(box instanceof HTMLElement)) throw new Error("the trace drew no rows box");
  return box;
}

/** Whether the rows are furled away, read off the inner wrapper. */
function furl(view: RenderResult): string {
  const inner = rowsBox(view).firstElementChild;
  if (!(inner instanceof HTMLElement)) throw new Error("the rows box is empty");
  return inner.style.visibility;
}

function rowsOf(count: number): TraceRowView[] {
  return Array.from({ length: count }, (_unused, index) =>
    row({ key: `call_${index}`, toolCallId: `call_${index}` }),
  );
}

describe("Trace", () => {
  it("sets no outer margin, so the message container owns the rhythm", () => {
    const view = draw(run({}));
    expect(view.getByTestId("turn-trace").className).toBe("");
  });

  it("counts one step in the singular", () => {
    draw(run({ groups: [group({ rows: rowsOf(1) })] }));
    expect(screen.getByTestId("turn-trace-summary")).toHaveTextContent("1 step");
  });

  it("counts seven steps in the plural", () => {
    draw(run({ groups: [group({ rows: rowsOf(7) })] }));
    expect(screen.getByTestId("turn-trace-summary")).toHaveTextContent("7 steps");
  });

  it("says Working... while a call is still running", () => {
    const rows = [
      ...rowsOf(6),
      row({ key: "call_7", toolCallId: "call_7", status: "running" }),
    ];
    draw(run({ groups: [group({ rows })], running: true }));
    expect(screen.getByTestId("turn-trace-summary")).toHaveTextContent("Working...");
  });

  it("counts the steps of a run its turn stopped, and never says Working...", () => {
    const rows = [
      ...rowsOf(6),
      row({ key: "call_7", toolCallId: "call_7", status: "stopped", summary: null }),
    ];
    const view = draw(
      run({
        groups: [group({ key: "sa_1", phase: "frame", state: "cancelled", rows })],
      }),
    );
    expect(view.getByTestId("turn-trace-summary")).toHaveTextContent("7 steps");
    expect(view.getByTestId("turn-trace-toggle")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("says Waiting for you while no call runs and one waits on the user", () => {
    const rows = [
      ...rowsOf(6),
      row({ key: "call_7", toolCallId: "call_7", status: "awaiting-approval" }),
    ];
    draw(run({ groups: [group({ rows })], running: true }));
    expect(screen.getByTestId("turn-trace-summary")).toHaveTextContent(
      "Waiting for you",
    );
  });

  it("holds the toggle, the summary and the rows under one testid", () => {
    const view = draw(
      run({ groups: [group({ rows: [row({ status: "running" })] })], running: true }),
    );
    const trace = view.getByTestId("turn-trace");
    expect(within(trace).getByTestId("turn-trace-toggle")).toBeInTheDocument();
    expect(within(trace).getByTestId("turn-trace-summary")).toHaveTextContent(
      "Working...",
    );
    expect(within(trace).getAllByTestId("trace-row")).toHaveLength(1);
  });

  it("starts open mid-run and closed when it mounts settled", () => {
    const open = draw(run({ running: true }));
    expect(rowsBox(open).style.gridTemplateRows).toBe("1fr");
    open.unmount();

    const settled = draw(run({ running: false }));
    expect(rowsBox(settled).style.gridTemplateRows).toBe("0fr");
  });

  it("stays open when the run settles under it", () => {
    const view = draw(run({ running: true }));
    expect(rowsBox(view).style.gridTemplateRows).toBe("1fr");

    view.rerender(element(run({ running: false })));
    expect(rowsBox(view).style.gridTemplateRows).toBe("1fr");
  });

  it("stays closed by the reader even when a new run starts", () => {
    const view = draw(run({ running: true }));
    fireEvent.click(view.getByTestId("turn-trace-toggle"));
    expect(rowsBox(view).style.gridTemplateRows).toBe("0fr");

    view.rerender(element(run({ running: true, rowCount: 3 })));
    expect(rowsBox(view).style.gridTemplateRows).toBe("0fr");
  });

  it("lets the reader close a running trace and open a settled one", () => {
    const open = draw(run({ running: true }));
    fireEvent.click(open.getByTestId("turn-trace-toggle"));
    expect(rowsBox(open).style.gridTemplateRows).toBe("0fr");
    open.unmount();

    const settled = draw(run({ running: false }));
    fireEvent.click(settled.getByTestId("turn-trace-toggle"));
    expect(rowsBox(settled).style.gridTemplateRows).toBe("1fr");
  });

  it("keeps the rows on screen until the collapse has finished", () => {
    const view = draw(run({ running: true }));
    expect(furl(view)).toBe("visible");

    fireEvent.click(view.getByTestId("turn-trace-toggle"));
    expect(furl(view)).toBe("visible");

    fireEvent.transitionEnd(rowsBox(view));
    expect(furl(view)).toBe("hidden");
  });

  it("puts the rows back on screen the moment the reader opens it", () => {
    const view = draw(run({ running: false }));
    expect(furl(view)).toBe("hidden");

    fireEvent.click(view.getByTestId("turn-trace-toggle"));
    expect(furl(view)).toBe("visible");
  });

  it("leaves the rows alone when the opening transition ends", () => {
    const view = draw(run({ running: false }));
    fireEvent.click(view.getByTestId("turn-trace-toggle"));
    fireEvent.transitionEnd(rowsBox(view));
    expect(furl(view)).toBe("visible");
  });

  it("gives a turn the Lead did alone no heading at all", () => {
    const view = draw(run({}));
    expect(view.queryAllByTestId("trace-group-label")).toHaveLength(0);
    expect(view.getAllByTestId("trace-row")).toHaveLength(1);
  });

  it("labels each group through the one shared phase label set", () => {
    const view = draw(
      run({
        groups: [
          group({}),
          group({ key: "sa_1", phase: "frame" }),
          group({ key: "sa_2", phase: "build" }),
          group({ key: "lead2" }),
        ],
      }),
    );
    expect(
      view.getAllByTestId("trace-group-label").map((node) => node.textContent),
    ).toEqual(["Assistant", "Planning", "Building", "Assistant"]);
  });

  it("falls back to the raw phase when no label is registered", () => {
    draw(run({ groups: [group({ key: "sa_1", phase: "triage" })] }));
    expect(screen.getByTestId("trace-group-label")).toHaveTextContent("triage");
  });

  it("takes a host's own label set when one is given", () => {
    render(
      <Trace
        run={run({ groups: [group({ key: "sa_1", phase: "frame" })] })}
        showRaw={false}
        showUsage={false}
        labelFor={(phase) => `phase:${phase}`}
        nameFor={(name) => name}
      />,
    );
    expect(screen.getByTestId("trace-group-label")).toHaveTextContent("phase:frame");
  });

  it("prints no usage at all when the dev flag is off", () => {
    const view = draw(
      run({
        groups: [
          group({ key: "sa_1", phase: "frame", tokens: 12300, costUsd: "0.004" }),
        ],
      }),
      false,
    );
    expect(view.queryAllByTestId("trace-group-usage")).toHaveLength(0);
  });

  it("prints the group's tokens and cost as an ASCII pair when the flag is on", () => {
    const view = draw(
      run({
        groups: [
          group({ key: "sa_1", phase: "frame", tokens: 12300, costUsd: "0.004" }),
        ],
      }),
      true,
    );
    expect(view.getByTestId("trace-group-usage")).toHaveTextContent("12.3K, $0.004");
  });

  it("prints no usage for a group that spent nothing", () => {
    const view = draw(
      run({
        groups: [group({ key: "sa_1", phase: "frame", tokens: 0, costUsd: "0" })],
      }),
      true,
    );
    expect(view.queryAllByTestId("trace-group-usage")).toHaveLength(0);
  });

  it("prints the turn's model and totals on the summary row when the flag is on", () => {
    const view = render(
      <Trace
        run={run({})}
        showRaw={false}
        showUsage
        nameFor={(name) => name}
        usage={{ model: "gpt-5.6-luna", tokens: 54100, costUsd: "0.0171" }}
      />,
    );
    const line = view.getByTestId("trace-usage");
    expect(line).toHaveTextContent("gpt-5.6-luna - 54.1K, $0.02");
    expect(line).toHaveAttribute("title", "This turn");
    expect(view.getByTestId("turn-trace-toggle").contains(line)).toBe(true);
  });

  it("prints no turn usage when the dev flag is off", () => {
    const view = render(
      <Trace
        run={run({})}
        showRaw={false}
        showUsage={false}
        nameFor={(name) => name}
        usage={{ model: "gpt-5.6-luna", tokens: 54100, costUsd: "0.0171" }}
      />,
    );
    expect(view.queryAllByTestId("trace-usage")).toHaveLength(0);
  });

  it("prints no turn usage when the run carries none", () => {
    const view = draw(run({}), true);
    expect(view.queryAllByTestId("trace-usage")).toHaveLength(0);
  });

  it("marks a sub-agent group with the data part testid it came from", () => {
    const view = draw(run({ groups: [group({ key: "sa_1", phase: "frame" })] }));
    const call = view.getByTestId("data-sub-agent-call");
    expect(within(call).getByTestId("trace-group-label")).toHaveTextContent("Planning");
  });

  it("puts the approval the run is waiting on after the last group", () => {
    const view = render(
      <Trace
        run={run({ groups: [group({}), group({ key: "sa_1", phase: "frame" })] })}
        showRaw={false}
        showUsage={false}
        nameFor={(name) => name}
        approval={<div data-testid="approval-slot">approve me</div>}
      />,
    );
    const slot = view.getByTestId("approval-slot");
    const groups = view.getAllByTestId("trace-group");
    const lastGroup = groups[groups.length - 1];
    if (lastGroup === undefined) throw new Error("the trace drew no group");
    expect(
      lastGroup.compareDocumentPosition(slot) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeGreaterThan(0);
  });
});
