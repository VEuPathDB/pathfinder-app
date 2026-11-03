/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AuditRunView } from "@pathfinder/shared/generated/types/AuditRunView";
import type { RunHalt } from "@pathfinder/shared/generated/types/RunHalt";

import { SAMPLE_RUN, SAMPLE_WORDS } from "./__fixtures__/sampleRun";
import { stagesOf } from "./runState";
import { StageProgress } from "./StageProgress";

function stopped(halt: RunHalt): AuditRunView {
  return {
    ...SAMPLE_RUN,
    run: { ...SAMPLE_RUN.run, phase: "halted" },
    action: "resume",
    halt,
  };
}

function waiting(message: string): AuditRunView {
  const stages = stagesOf(SAMPLE_RUN).map((stage, index) =>
    index === stagesOf(SAMPLE_RUN).length - 1
      ? { ...stage, finished: false, done: 1, total: 4, message }
      : stage,
  );
  return {
    ...SAMPLE_RUN,
    run: { ...SAMPLE_RUN.run, phase: "running" },
    stages: { ...SAMPLE_RUN.stages, stages },
  };
}

function show(view: AuditRunView) {
  render(<StageProgress view={view} words={SAMPLE_WORDS} />);
}

describe("StageProgress", () => {
  it("shows each stage done with its requests on a finished run", () => {
    show(SAMPLE_RUN);
    expect(
      screen.getByRole("heading", { level: 2, name: "Progress" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/^Finished$/);
    const confirm = screen.getByRole("progressbar", {
      name: "Check candidates in the DNA",
    });
    expect([confirm.getAttribute("value"), confirm.getAttribute("max")]).toEqual([
      "6",
      "8",
    ]);
    expect(screen.getAllByText("Done")).toHaveLength(4);
    expect(
      screen.getByText(
        `9 site requests, ${String(SAMPLE_RUN.storeReads)} genome-store reads`,
      ),
    ).toBeInTheDocument();
  });

  it("states the units the run left and the review line", () => {
    show(SAMPLE_RUN);
    expect(
      screen.getByText("The site did not answer: 1 finding and 1 piece of evidence"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reviewed and summarized: 5 of 5 findings"),
    ).toBeInTheDocument();
  });

  it("states reviews that run and a message of reviews that stopped", () => {
    show({
      ...SAMPLE_RUN,
      reviewsRunning: true,
      action: null,
      reviewState: {
        status: "reviewing",
        text: "Reviewing findings",
        done: 2,
        total: 5,
        message: "",
      },
    });
    expect(screen.getByText("Reviewing findings: 2 of 5 findings")).toBeInTheDocument();
  });

  it("appends the message of a review state that holds one", () => {
    show({
      ...SAMPLE_RUN,
      reviewState: {
        status: "stopped",
        text: "Reviews stopped",
        done: 1,
        total: 5,
        message: "the model refused",
      },
    });
    expect(
      screen.getByText("Reviews stopped: 1 of 5 findings: the model refused"),
    ).toBeInTheDocument();
  });

  it("states no review line for a run with no review state", () => {
    show({ ...SAMPLE_RUN, reviewState: null });
    expect(screen.queryByText(/of 5 findings/)).toBe(null);
  });

  it("says why a run stopped for its sign-in", () => {
    show(stopped({ kind: "sign_in", detail: "sign-in needed" }));
    expect(screen.getByRole("status")).toHaveTextContent(/^Stopped$/);
    expect(
      screen.getByText(
        "The audit needs your VEuPathDB sign-in. Sign in on the site, then resume it.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Technical detail")).toBe(null);
  });

  it("keeps the error of a task that failed behind a disclosure", async () => {
    const detail = "the audit job failed: KeyError: An internal error occurred";
    show(stopped({ kind: "task_failed", detail }));
    expect(
      screen.getByText(
        "The audit task stopped on an error. Resume it to go on from the last unit it finished.",
      ),
    ).toBeInTheDocument();
    const disclosure = screen.getByText("Technical detail").closest("details");
    expect(disclosure).not.toHaveAttribute("open");
    await userEvent.click(screen.getByText("Technical detail"));
    expect(disclosure).toHaveAttribute("open");
    expect(screen.getByText(detail)).toBeVisible();
  });

  it("says what a running stage waits for", () => {
    show(waiting("Waiting for PlasmoDB"));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Running: Waiting for PlasmoDB",
    );
    expect(screen.getByText("1 of 4")).toBeInTheDocument();
  });

  it("fills a finished stage that held no units", () => {
    const empty = stagesOf(SAMPLE_RUN).map((stage) => ({
      ...stage,
      done: 0,
      total: 0,
    }));
    show({ ...SAMPLE_RUN, stages: { ...SAMPLE_RUN.stages, stages: empty } });
    const bar = screen.getByRole("progressbar", { name: "Find candidates" });
    expect([bar.getAttribute("value"), bar.getAttribute("max")]).toEqual(["1", "1"]);
  });

  it("states the units the site refused for the sign-in", () => {
    show({
      ...SAMPLE_RUN,
      left: { ...SAMPLE_RUN.left, refused: 2 },
    });
    expect(
      screen.getByText("Refused for your sign-in, and read again on a retry: 2 units"),
    ).toBeInTheDocument();
  });
});
