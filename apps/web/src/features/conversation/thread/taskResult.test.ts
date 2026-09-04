import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { messageAnchorId, taskResultHref } from "./taskResult";

function assistant(id: string, parts: UIMessage["parts"]): UIMessage {
  return { id, role: "assistant", parts };
}

const FIGURES: ReadonlySet<string> = new Set([
  "data-enrichment-results",
  "data-eda.viz",
]);

function completed(taskId: string): UIMessage["parts"][number] {
  return { type: "data-task-completed", data: { taskId, status: "success" } };
}

describe("the link from a task to what it produced", () => {
  it("names nothing while the task is still running", () => {
    const messages = [
      assistant("m1", [
        { type: "data-background-task-started", data: { taskId: "t1" } },
      ]),
    ];
    expect(taskResultHref(messages, "t1", FIGURES)).toBe(null);
  });

  it("points at the turn that carries the figure the task produced", () => {
    const messages = [
      assistant("m1", [
        { type: "data-background-task-started", data: { taskId: "t1" } },
        completed("t1"),
      ]),
      assistant("m2", [{ type: "data-enrichment-results", data: {} }]),
    ];
    expect(taskResultHref(messages, "t1", FIGURES)).toBe(`#${messageAnchorId("m2")}`);
  });

  it("points at the prose turn when the result drew no figure", () => {
    const messages = [
      assistant("m1", [completed("t1")]),
      assistant("m2", [{ type: "text", text: "The comparison finished." }]),
    ];
    expect(taskResultHref(messages, "t1", FIGURES)).toBe(`#${messageAnchorId("m2")}`);
  });

  it("points at the completion's own turn when it carries the figure", () => {
    const messages = [
      assistant("m1", [completed("t1"), { type: "data-eda.viz", data: {} }]),
    ];
    expect(taskResultHref(messages, "t1", FIGURES)).toBe(`#${messageAnchorId("m1")}`);
  });

  it("ignores another task's completion", () => {
    const messages = [
      assistant("m1", [completed("t2")]),
      assistant("m2", [{ type: "text", text: "done" }]),
    ];
    expect(taskResultHref(messages, "t1", FIGURES)).toBe(null);
  });

  it("names nothing when the completion turn produced nothing to read", () => {
    const messages = [assistant("m1", [completed("t1")])];
    expect(taskResultHref(messages, "t1", FIGURES)).toBe(null);
  });

  it("ignores the prose the turn wrote before it started the task", () => {
    const messages = [
      assistant("m1", [
        { type: "text", text: "I will run the control tests." },
        { type: "data-background-task-started", data: { taskId: "t1" } },
        completed("t1"),
      ]),
    ];
    expect(taskResultHref(messages, "t1", FIGURES)).toBe(null);
  });

  it("names the completion's own turn for prose written after it", () => {
    const messages = [
      assistant("m1", [
        { type: "text", text: "I will run the control tests." },
        completed("t1"),
        { type: "text", text: "Both steps recovered their controls." },
      ]),
    ];
    expect(taskResultHref(messages, "t1", FIGURES)).toBe(`#${messageAnchorId("m1")}`);
  });
});
