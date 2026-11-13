/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { startAuditRun } from "@strategist/shared/generated/hooks/useStartAuditRun";
import type { AuditRunView } from "@strategist/shared/generated/types/AuditRunView";

vi.mock("@strategist/shared/generated/hooks/useStartAuditRun", () => ({
  startAuditRun: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { createTestWrapper } from "@/lib/query/testing";

import { SAMPLE_RUN, SAMPLE_RUN_ID } from "./__fixtures__/sampleRun";
import { auditRunOptions } from "./api";
import { RunAction } from "./RunAction";

function renderAction(view: AuditRunView) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(auditRunOptions(view.run.id).queryKey, view);
  const rendered = render(<RunAction view={view} />, { wrapper: Wrapper });
  return { queryClient, container: rendered.container };
}

describe("RunAction", () => {
  beforeEach(() => {
    vi.mocked(startAuditRun).mockReset();
    vi.mocked(toast.error).mockReset();
  });

  it("retries what a finished run left unread and shows the run it returns", async () => {
    const running: AuditRunView = {
      ...SAMPLE_RUN,
      run: { ...SAMPLE_RUN.run, phase: "running" },
      action: null,
      left: { genomes: 0, findings: 0, evidence: 0, total: 0 },
    };
    vi.mocked(startAuditRun).mockResolvedValue(running);
    const { queryClient } = renderAction(SAMPLE_RUN);
    await userEvent.click(
      screen.getByRole("button", { name: "Retry what was not read" }),
    );
    expect(vi.mocked(startAuditRun)).toHaveBeenCalledWith(
      SAMPLE_RUN_ID,
      { action: "retry" },
      { siteId: "plasmodb" },
    );
    await waitFor(() => {
      expect(queryClient.getQueryData(auditRunOptions(SAMPLE_RUN_ID).queryKey)).toEqual(
        running,
      );
    });
  });

  it("says why a start was refused", async () => {
    vi.mocked(startAuditRun).mockRejectedValue(
      new Error("this run offers a resume, not a retry"),
    );
    renderAction(SAMPLE_RUN);
    await userEvent.click(
      screen.getByRole("button", { name: "Retry what was not read" }),
    );
    await waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith("The audit did not start", {
        description: "this run offers a resume, not a retry",
      });
    });
  });

  it("offers resume on a stopped run and nothing on a running one", () => {
    renderAction({ ...SAMPLE_RUN, action: "resume" });
    expect(screen.getByRole("button", { name: "Resume the audit" })).toBeEnabled();
    cleanup();
    const { container } = renderAction({ ...SAMPLE_RUN, action: null });
    expect(container).toBeEmptyDOMElement();
  });

  it("says why a run whose conversation was deleted cannot start again", () => {
    renderAction({
      ...SAMPLE_RUN,
      action: null,
      run: { ...SAMPLE_RUN.run, conversationId: null },
    });
    expect(
      screen.getByText(
        "The conversation that started this audit was deleted, so it cannot start again.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBe(null);
  });
});
