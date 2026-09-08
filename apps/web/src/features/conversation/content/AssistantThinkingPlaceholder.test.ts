import { describe, expect, it } from "vitest";

import {
  selectPartsFingerprint,
  selectStatusLabel,
} from "./AssistantThinkingPlaceholder";
import { formatElapsed, statusLineWith } from "./statusClock";

/**
 * A turn that waits for a worker sends no chunks of its own, so the running
 * message says only "Thinking..." while nothing is happening yet. The
 * dispatcher stamps the waiting turn with `data-turn-status {label: "Queued"}`
 * and this selector is what puts that word on screen.
 */

function running(...labels: (string | null)[]) {
  return {
    status: { type: "running" },
    content: labels.map((label) =>
      label === null
        ? { type: "text", text: "hello" }
        : { type: "data-turn-status", data: { label } },
    ),
  };
}

describe("selectStatusLabel", () => {
  it("says Queued while the turn waits for a worker", () => {
    expect(selectStatusLabel(running("Queued"))).toBe("Queued");
  });

  it("moves on to the label the worker sends when it starts the turn", () => {
    expect(selectStatusLabel(running("Queued", "Starting the turn"))).toBe(
      "Starting the turn",
    );
  });

  it("keeps the last label a turn reported", () => {
    expect(
      selectStatusLabel(
        running(
          "Queued",
          "Starting the turn",
          "Recalling earlier work",
          "Reading the thread",
        ),
      ),
    ).toBe("Reading the thread");
  });

  it("falls back to Thinking... when the turn reported no status", () => {
    expect(selectStatusLabel(running(null))).toBe("Thinking...");
  });

  it("ignores an empty label", () => {
    expect(selectStatusLabel(running("Queued", ""))).toBe("Queued");
  });

  it("also accepts the generic data part shape", () => {
    expect(
      selectStatusLabel({
        status: { type: "running" },
        content: [{ type: "data", name: "turn-status", data: { label: "Queued" } }],
      }),
    ).toBe("Queued");
  });

  it("says nothing for a message that is no longer running", () => {
    expect(
      selectStatusLabel({ ...running("Queued"), status: { type: "complete" } }),
    ).toBe(null);
    expect(selectStatusLabel(undefined)).toBe(null);
  });
});

/**
 * `build_strategy` runs no sub-agent, so it sends no status label of its own.
 * The label follows the dispatch cards instead, which is what the trace draws.
 */
describe("selectStatusLabel follows the phase the trace shows", () => {
  function dispatch(toolCallId: string, phase: string, state: string) {
    return { type: "data-sub-agent-call", data: { toolCallId, phase, state } };
  }

  it("says Building while the build dispatch is open, not the last frame label", () => {
    expect(
      selectStatusLabel({
        status: { type: "running" },
        content: [
          { type: "data-turn-status", data: { label: "Framing the strategy..." } },
          dispatch("c1", "frame", "started"),
          dispatch("c1", "frame", "completed"),
          dispatch("c2", "build", "started"),
        ],
      }),
    ).toBe("Building...");
  });

  it("returns to the reported label once every dispatch closed", () => {
    expect(
      selectStatusLabel({
        status: { type: "running" },
        content: [
          { type: "data-turn-status", data: { label: "Thinking..." } },
          dispatch("c2", "build", "started"),
          dispatch("c2", "build", "completed"),
        ],
      }),
    ).toBe("Thinking...");
  });
});

describe("formatElapsed", () => {
  it("writes seconds under a minute", () => {
    expect(formatElapsed(0)).toBe("0s");
    expect(formatElapsed(45)).toBe("45s");
  });

  it("writes minutes and seconds above a minute", () => {
    expect(formatElapsed(60)).toBe("1m 0s");
    expect(formatElapsed(160)).toBe("2m 40s");
  });

  it("writes ASCII only", () => {
    expect(formatElapsed(160)).not.toMatch(/[^\x20-\x7e]/);
  });
});

describe("statusLineWith", () => {
  it("leaves the label alone while the turn is still sending parts", () => {
    expect(statusLineWith("Planning...", 0)).toBe("Planning...");
    expect(statusLineWith("Planning...", 9)).toBe("Planning...");
  });

  it("appends the elapsed time once the turn goes quiet", () => {
    expect(statusLineWith("Planning...", 10)).toBe("Planning, 10s");
    expect(statusLineWith("Planning...", 160)).toBe("Planning, 2m 40s");
  });

  it("appends to a label that carries no trailing dots", () => {
    expect(statusLineWith("Queued", 160)).toBe("Queued, 2m 40s");
  });
});

describe("selectPartsFingerprint", () => {
  it("changes when a part is appended", () => {
    const one = running("Queued");
    const two = running("Queued", null);
    expect(selectPartsFingerprint(one)).not.toBe(selectPartsFingerprint(two));
  });

  it("changes while the last text part streams, so the silence timer resets", () => {
    const short = running(null);
    const long = running(null);
    long.content[0] = { type: "text", text: "hello world, more tokens" };
    expect(selectPartsFingerprint(short)).not.toBe(selectPartsFingerprint(long));
  });

  it("is stable when nothing arrives", () => {
    const m = running("Queued", null);
    expect(selectPartsFingerprint(m)).toBe(selectPartsFingerprint(m));
  });
});
