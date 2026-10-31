import { readUIMessageStream, type UIMessage, type UIMessageChunk } from "ai";
import { describe, expect, it } from "vitest";

import { findToolApproval } from "./ToolApprovalControls";

const MESSAGE_ID = "0e405bd1-642c-40de-8f56-85b6e9f95f86";
const CALL_ID = "call_sweep";
const TOOL_NAME = "optimize_search_parameters";
const TASK_ID = "65b06057-eb29-48d4-88de-8c886d40aa1d";
const INPUT = {
  reply: "The strategy holds what the turn built, and one refinement is open.",
  budget: 6,
  wdk_step_id: 440230693,
  control_set_id: "7c0a51e2-0000-4000-8000-0000005bee75",
};

const ASKED: UIMessageChunk[] = [
  { type: "start", messageId: MESSAGE_ID },
  { type: "start-step" },
  { type: "finish-step" },
  { type: "text-start", id: `reply-${CALL_ID}` },
  { type: "text-delta", id: `reply-${CALL_ID}`, delta: INPUT.reply },
  { type: "text-end", id: `reply-${CALL_ID}` },
  { type: "tool-input-start", toolCallId: CALL_ID, toolName: TOOL_NAME },
  {
    type: "tool-input-available",
    toolCallId: CALL_ID,
    toolName: TOOL_NAME,
    input: INPUT,
  },
  { type: "tool-approval-request", approvalId: CALL_ID, toolCallId: CALL_ID },
  { type: "finish", finishReason: "other" },
];

const APPROVED_AND_PARKED: UIMessageChunk[] = [
  { type: "start", messageId: MESSAGE_ID },
  {
    type: "tool-input-available",
    toolCallId: CALL_ID,
    toolName: TOOL_NAME,
    input: INPUT,
  },
  {
    type: "data-background-task-started",
    data: { taskId: TASK_ID, toolName: TOOL_NAME, estimatedDurationSeconds: 900 },
  },
  { type: "finish-step" },
  { type: "finish", finishReason: "other" },
];

const COMPLETED: UIMessageChunk[] = [
  { type: "start", messageId: MESSAGE_ID },
  { type: "tool-input-start", toolCallId: CALL_ID, toolName: TOOL_NAME },
  {
    type: "tool-input-available",
    toolCallId: CALL_ID,
    toolName: TOOL_NAME,
    input: INPUT,
  },
  {
    type: "tool-output-available",
    toolCallId: CALL_ID,
    output: { result: { trials: 6 } },
  },
  { type: "finish", finishReason: "stop" },
];

const DENIED: UIMessageChunk[] = [
  { type: "start", messageId: MESSAGE_ID },
  { type: "tool-input-start", toolCallId: CALL_ID, toolName: TOOL_NAME },
  {
    type: "tool-input-available",
    toolCallId: CALL_ID,
    toolName: TOOL_NAME,
    input: INPUT,
  },
  { type: "tool-output-denied", toolCallId: CALL_ID },
  { type: "finish", finishReason: "stop" },
];

async function replayed(chunks: UIMessageChunk[]): Promise<UIMessage[]> {
  const stream = new ReadableStream<UIMessageChunk>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
  let last: UIMessage | undefined;
  for await (const message of readUIMessageStream({ stream })) last = message;
  if (last === undefined) throw new Error("the replay built no message");
  return [last];
}

describe("findToolApproval on a message the durable tail replays whole", () => {
  it("reads an approved call parked on its task as approved", async () => {
    const messages = await replayed([...ASKED, ...APPROVED_AND_PARKED]);
    expect(findToolApproval(messages, CALL_ID)?.decision).toBe("approved");
  });

  it("reads an approved call its task completed as approved", async () => {
    const messages = await replayed([...ASKED, ...APPROVED_AND_PARKED, ...COMPLETED]);
    expect(findToolApproval(messages, CALL_ID)?.decision).toBe("approved");
  });

  it("reads a refused call as denied", async () => {
    const messages = await replayed([...ASKED, ...DENIED]);
    expect(findToolApproval(messages, CALL_ID)?.decision).toBe("denied");
  });

  it("reads a call still waiting on the user as pending", async () => {
    const messages = await replayed(ASKED);
    expect(findToolApproval(messages, CALL_ID)?.decision).toBe("pending");
  });
});

describe("findToolApproval on a message the snapshot rebuilt", () => {
  const snapshot = (approved: boolean): UIMessage[] => [
    {
      id: MESSAGE_ID,
      role: "assistant",
      parts: [
        { type: "step-start" },
        {
          type: `tool-${TOOL_NAME}`,
          toolCallId: CALL_ID,
          state: "input-available",
          input: INPUT,
        },
        {
          type: "data-tool-approval",
          id: CALL_ID,
          data: { toolCallId: CALL_ID, approvalId: CALL_ID, approved },
        },
        {
          type: "data-background-task-started",
          data: { taskId: TASK_ID, toolName: TOOL_NAME, estimatedDurationSeconds: 900 },
        },
      ],
    },
  ];

  it("reads a running call's answer from its recorded approval", () => {
    const view = findToolApproval(snapshot(true), CALL_ID);
    expect([view?.approvalId, view?.decision]).toEqual([CALL_ID, "approved"]);
  });

  it("reads a recorded refusal as denied", () => {
    expect(findToolApproval(snapshot(false), CALL_ID)?.decision).toBe("denied");
  });
});
