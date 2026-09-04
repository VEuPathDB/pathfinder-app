import { describe, expect, it } from "vitest";
import { createActor } from "xstate";
import {
  STEP_LIFECYCLE_STATE_NAMES,
  initialStepSnapshot,
  seedStepMachine,
  stepMachine,
  type StepMachineContext,
} from "./stepMachine";
import type { ValidationErrors } from "@pathfinder/shared";

function startInState(
  state: "idle" | "valid" | "invalid" | "complete" | "failed",
  context?: Partial<StepMachineContext>,
) {
  const actor = createActor(stepMachine, {
    snapshot: seedStepMachine(state, context),
  });
  actor.start();
  return actor;
}

describe("stepMachine — initial state", () => {
  it("starts in idle with null context", () => {
    const actor = createActor(stepMachine);
    actor.start();
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("idle");
    expect(snap.context.estimatedSize).toBeNull();
    expect(snap.context.validationErrors).toBeNull();
    expect(snap.context.lastError).toBeNull();
  });
});

describe("stepMachine — VALIDATE transitions", () => {
  it("idle → validating on VALIDATE", () => {
    const actor = createActor(stepMachine);
    actor.start();
    actor.send({ type: "VALIDATE" });
    expect(actor.getSnapshot().value).toBe("validating");
  });

  it("valid → validating on VALIDATE", () => {
    const actor = startInState("valid", { estimatedSize: 100 });
    actor.send({ type: "VALIDATE" });
    expect(actor.getSnapshot().value).toBe("validating");
  });

  it("invalid → validating on VALIDATE", () => {
    const actor = startInState("invalid", {
      validationErrors: { general: ["bad"], byKey: {} },
    });
    actor.send({ type: "VALIDATE" });
    expect(actor.getSnapshot().value).toBe("validating");
  });

  it("complete → validating on VALIDATE", () => {
    const actor = startInState("complete", { estimatedSize: 42 });
    actor.send({ type: "VALIDATE" });
    expect(actor.getSnapshot().value).toBe("validating");
  });

  it("failed → validating on VALIDATE", () => {
    const actor = startInState("failed", { lastError: "boom" });
    actor.send({ type: "VALIDATE" });
    expect(actor.getSnapshot().value).toBe("validating");
  });
});

describe("stepMachine — VALIDATION_SUCCESS transitions", () => {
  it("validating → valid on VALIDATION_SUCCESS without estimatedSize", () => {
    const actor = createActor(stepMachine);
    actor.start();
    actor.send({ type: "VALIDATE" });
    actor.send({ type: "VALIDATION_SUCCESS" });
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("valid");
    expect(snap.context.validationErrors).toBeNull();
  });

  it("validating → valid on VALIDATION_SUCCESS, stores estimatedSize", () => {
    const actor = createActor(stepMachine);
    actor.start();
    actor.send({ type: "VALIDATE" });
    actor.send({ type: "VALIDATION_SUCCESS", estimatedSize: 250 });
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("valid");
    expect(snap.context.estimatedSize).toBe(250);
    expect(snap.context.validationErrors).toBeNull();
  });

  it("clears prior validationErrors on VALIDATION_SUCCESS", () => {
    const actor = startInState("invalid", {
      validationErrors: { general: ["err"], byKey: {} },
    });
    actor.send({ type: "VALIDATE" });
    actor.send({ type: "VALIDATION_SUCCESS" });
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("valid");
    expect(snap.context.validationErrors).toBeNull();
  });
});

describe("stepMachine — VALIDATION_ERROR transitions", () => {
  it("validating → invalid with error payload", () => {
    const errors: ValidationErrors = {
      general: ["Missing required param"],
      byKey: { taxon: ["required"] },
    };
    const actor = createActor(stepMachine);
    actor.start();
    actor.send({ type: "VALIDATE" });
    actor.send({ type: "VALIDATION_ERROR", errors });
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("invalid");
    expect(snap.context.validationErrors).toEqual(errors);
  });
});

describe("stepMachine — RUN_COUNTS / COUNTS_READY transitions", () => {
  it("valid → running on RUN_COUNTS", () => {
    const actor = startInState("valid", { estimatedSize: 10 });
    actor.send({ type: "RUN_COUNTS" });
    expect(actor.getSnapshot().value).toBe("running");
  });

  it("complete → running on RUN_COUNTS", () => {
    const actor = startInState("complete", { estimatedSize: 10 });
    actor.send({ type: "RUN_COUNTS" });
    expect(actor.getSnapshot().value).toBe("running");
  });

  it("failed → running on RUN_COUNTS so a failed count can be retried directly", () => {
    const actor = startInState("failed", { lastError: "Network timeout" });
    actor.send({ type: "RUN_COUNTS" });
    expect(actor.getSnapshot().value).toBe("running");
  });

  it("idle → RUN_COUNTS is ignored: counts require a validated step", () => {
    const actor = createActor(stepMachine);
    actor.start();
    actor.send({ type: "RUN_COUNTS" });
    expect(actor.getSnapshot().value).toBe("idle");
  });

  it("running → complete on COUNTS_READY, stores count", () => {
    const actor = startInState("valid", { estimatedSize: 5 });
    actor.send({ type: "RUN_COUNTS" });
    actor.send({ type: "COUNTS_READY", count: 123 });
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("complete");
    expect(snap.context.estimatedSize).toBe(123);
  });

  it("COUNTS_READY with null clears count but still marks complete", () => {
    const actor = startInState("valid", { estimatedSize: 7 });
    actor.send({ type: "RUN_COUNTS" });
    actor.send({ type: "COUNTS_READY", count: null });
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("complete");
    expect(snap.context.estimatedSize).toBeNull();
  });
});

describe("stepMachine — RUN_ERROR transitions", () => {
  it("running → failed on RUN_ERROR, stores message", () => {
    const actor = startInState("valid");
    actor.send({ type: "RUN_COUNTS" });
    actor.send({ type: "RUN_ERROR", message: "Network timeout" });
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("failed");
    expect(snap.context.lastError).toBe("Network timeout");
  });

  it("validating → failed on RUN_ERROR (server/network failure during validation)", () => {
    const actor = createActor(stepMachine);
    actor.start();
    actor.send({ type: "VALIDATE" });
    actor.send({ type: "RUN_ERROR", message: "500 Internal" });
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("failed");
    expect(snap.context.lastError).toBe("500 Internal");
  });
});

describe("stepMachine — RESET transitions", () => {
  it("RESET from any state returns to idle with cleared context", () => {
    const states: Array<"valid" | "invalid" | "complete" | "failed"> = [
      "valid",
      "invalid",
      "complete",
      "failed",
    ];
    for (const state of states) {
      const actor = startInState(state, {
        estimatedSize: 99,
        validationErrors: { general: ["x"], byKey: {} },
        lastError: "old",
      });
      actor.send({ type: "RESET" });
      const snap = actor.getSnapshot();
      expect(snap.value).toBe("idle");
      expect(snap.context.estimatedSize).toBeNull();
      expect(snap.context.validationErrors).toBeNull();
      expect(snap.context.lastError).toBeNull();
    }
  });
});

describe("stepMachine — seedStepMachine", () => {
  it("seeds state with provided context", () => {
    const actor = createActor(stepMachine, {
      snapshot: seedStepMachine("complete", { estimatedSize: 77 }),
    });
    actor.start();
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("complete");
    expect(snap.context.estimatedSize).toBe(77);
  });

  it("seeds idle state by default with empty context", () => {
    const actor = createActor(stepMachine, {
      snapshot: seedStepMachine("idle"),
    });
    actor.start();
    const snap = actor.getSnapshot();
    expect(snap.value).toBe("idle");
    expect(snap.context.estimatedSize).toBeNull();
  });
});

describe("stepMachine — initialStepSnapshot", () => {
  it("returns a pristine idle snapshot when given no seed", () => {
    const snap = initialStepSnapshot();
    expect(snap.value).toBe("idle");
    expect(snap.context).toEqual({
      estimatedSize: null,
      validationErrors: null,
      lastError: null,
    });
  });

  it("merges a context-only seed onto the idle state, defaulting the untouched fields", () => {
    const snap = initialStepSnapshot({ context: { estimatedSize: 7 } });
    expect(snap.value).toBe("idle");
    expect(snap.context.estimatedSize).toBe(7);
    expect(snap.context.validationErrors).toBeNull();
    expect(snap.context.lastError).toBeNull();
  });

  it("honours a seeded state together with its context", () => {
    const snap = initialStepSnapshot({
      state: "failed",
      context: { lastError: "boom" },
    });
    expect(snap.value).toBe("failed");
    expect(snap.context.lastError).toBe("boom");
    expect(snap.context.estimatedSize).toBeNull();
  });
});

describe("stepMachine — matches helper behavior", () => {
  it("snapshot.matches returns true for the current state", () => {
    const actor = createActor(stepMachine);
    actor.start();
    actor.send({ type: "VALIDATE" });
    expect(actor.getSnapshot().matches("validating")).toBe(true);
    expect(actor.getSnapshot().matches("idle")).toBe(false);
  });
});

describe("stepMachine — the exported state names are the machine's own", () => {
  it("lists exactly the states the machine defines", () => {
    // useStepSnapshot narrows a raw StateValue against this list. A name that
    // drifts out of the machine would silently read back as "idle", so the
    // canvas would show a step as untouched while it was actually running.
    expect([...STEP_LIFECYCLE_STATE_NAMES].sort()).toEqual(
      Object.keys(stepMachine.states).sort(),
    );
  });
});
