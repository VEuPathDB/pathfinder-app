/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { dataPartRenderers } from "./dataPartRegistry";
import type { ReasoningMessagePartProps } from "@assistant-ui/react";

import { ReasoningPart, selectAssistantErrorDetail } from "./MessageRenderer";
import { USER_QUESTION_ANSWERS_PART_TYPE } from "../rail/consultActions";
import { ChatHelpersProvider, type ChatHelpers } from "../runtime/chatHelpersContext";

const STUB_CHAT = { messages: [], status: "ready" } as unknown as ChatHelpers;

describe("selectAssistantErrorDetail", () => {
  const failed = { type: "incomplete", reason: "error", error: "boom" };

  it("reads the live error off a message that carries no failure part", () => {
    expect(
      selectAssistantErrorDetail({ status: failed, content: [{ type: "text" }] }),
    ).toBe("boom");
  });

  it("says nothing once the turn carries its own failure part", () => {
    // The part is durable and says the same thing, so the live card would be
    // a second copy of one failure.
    expect(
      selectAssistantErrorDetail({
        status: failed,
        content: [{ type: "text" }, { type: "data-turn-failed" }],
      }),
    ).toBe(null);
  });

  it("also recognises the generic data part shape", () => {
    expect(
      selectAssistantErrorDetail({
        status: failed,
        content: [{ type: "data", name: "turn-failed" }],
      }),
    ).toBe(null);
  });

  it("says nothing for a turn the user stopped", () => {
    expect(
      selectAssistantErrorDetail({
        status: { type: "incomplete", reason: "cancelled" },
        content: [],
      }),
    ).toBe(null);
  });

  it("shows the field message a chat 422 carries, never the raw body", () => {
    const body = JSON.stringify({
      type: "about:blank",
      title: "Invalid plan",
      status: 422,
      code: "VALIDATION_ERROR",
      errors: [{ path: "recordType", message: "Record type is required" }],
    });
    expect(
      selectAssistantErrorDetail({
        status: { type: "incomplete", reason: "error", error: body },
        content: [],
      }),
    ).toBe("Record type is required");
  });

  it("says nothing for a turn that finished", () => {
    expect(
      selectAssistantErrorDetail({ status: { type: "complete" }, content: [] }),
    ).toBe(null);
  });
});

describe("dataPartRenderers", () => {
  it("registers the answers part the consult carousel posts back", () => {
    const shortName = USER_QUESTION_ANSWERS_PART_TYPE.replace(/^data-/, "");
    expect(Object.hasOwn(dataPartRenderers, shortName)).toBe(true);
  });

  it("keeps strategy-revision registered for SupersededBadge", () => {
    expect(Object.hasOwn(dataPartRenderers, "strategy-revision")).toBe(true);
  });

  it("has no entry for kinds nothing emits", () => {
    expect(Object.hasOwn(dataPartRenderers, "plan-slot-answers")).toBe(false);
    expect(Object.hasOwn(dataPartRenderers, "decision-answers")).toBe(false);
    expect(Object.hasOwn(dataPartRenderers, "tool-approval-request")).toBe(false);
    expect(Object.hasOwn(dataPartRenderers, "tool-approval-result")).toBe(false);
  });
});

function renderPart(shortName: string, data: unknown) {
  const Part = dataPartRenderers[shortName]!;
  return render(
    <ChatHelpersProvider value={STUB_CHAT}>
      <Part type="data" name={shortName} data={data} status={{ type: "complete" }} />
    </ChatHelpersProvider>,
  );
}

describe("dataPartRenderers dispatch", () => {
  it("dispatches data-memory-retrieved to the correct component", () => {
    renderPart("memory-retrieved", {
      memories: [{ key: "k1", kind: "gene_set_note", name: "Kinases", score: 1 }],
    });
    expect(screen.getByTestId("data-memory-retrieved")).toBeInTheDocument();
  });

  it("renders nothing for a task part the started card owns", () => {
    const { container } = renderPart("task-completed", {
      taskId: "t1",
      status: "success",
    });
    expect(container.innerHTML).toBe("");
  });

  it("dispatches data-strategy-link to the correct component", () => {
    renderPart("strategy-link", {
      strategyId: "s1",
      url: "https://plasmodb.org/s1",
      title: "Test",
    });
    expect(screen.getByTestId("data-strategy-link")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Test" })).toBeInTheDocument();
  });

  it("dispatches data-gene-set to the correct component", () => {
    renderPart("gene-set", {
      geneSetId: "gs1",
      name: "Test Set",
      geneCount: 42,
      siteId: "plasmodb",
    });
    expect(screen.getByTestId("data-gene-set")).toBeInTheDocument();
  });
});

describe("ReasoningPart", () => {
  const settled = (text: string): ReasoningMessagePartProps => ({
    type: "reasoning",
    text,
    status: { type: "complete" },
  });

  it("renders nothing for a reasoning part that settled with no text", () => {
    const { container } = render(<ReasoningPart {...settled("")} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders the disclosure once there is reasoning text", () => {
    render(<ReasoningPart {...settled("weighing the filter")} />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("keeps the disclosure while an empty part is still streaming", () => {
    const streaming: ReasoningMessagePartProps = {
      type: "reasoning",
      text: "",
      status: { type: "running" },
    };
    const { container } = render(<ReasoningPart {...streaming} />);
    expect(container.innerHTML).not.toBe("");
  });
});
