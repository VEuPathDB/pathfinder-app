// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BranchOrRevertDialog } from "./BranchOrRevertDialog";

describe("BranchOrRevertDialog", () => {
  it("fires onBranch when branch clicked", async () => {
    const onBranch = vi.fn();
    render(
      <BranchOrRevertDialog
        open
        canBranch
        pending={false}
        error={null}
        onBranch={onBranch}
        onRevert={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByTestId("edit-branch-button"));
    expect(onBranch).toHaveBeenCalledTimes(1);
  });

  it("fires onRevert when revert clicked", async () => {
    const onRevert = vi.fn();
    render(
      <BranchOrRevertDialog
        open
        canBranch
        pending={false}
        error={null}
        onBranch={vi.fn()}
        onRevert={onRevert}
        onCancel={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByTestId("edit-revert-button"));
    expect(onRevert).toHaveBeenCalledTimes(1);
  });

  it("disables branch when canBranch is false", () => {
    render(
      <BranchOrRevertDialog
        open
        canBranch={false}
        pending={false}
        error={null}
        onBranch={vi.fn()}
        onRevert={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId("edit-branch-button")).toBeDisabled();
    expect(screen.getByTestId("edit-revert-button")).toBeEnabled();
  });

  it("disables both actions while pending", () => {
    render(
      <BranchOrRevertDialog
        open
        canBranch
        pending
        error={null}
        onBranch={vi.fn()}
        onRevert={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId("edit-branch-button")).toBeDisabled();
    expect(screen.getByTestId("edit-revert-button")).toBeDisabled();
  });

  it("renders the server's refusal and keeps both actions clickable", () => {
    render(
      <BranchOrRevertDialog
        open
        canBranch
        pending={false}
        error="Target message not found"
        onBranch={vi.fn()}
        onRevert={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId("edit-dialog-error")).toHaveTextContent(
      "Target message not found",
    );
    expect(screen.getByTestId("edit-revert-button")).toBeEnabled();
    expect(screen.getByTestId("edit-branch-button")).toBeEnabled();
  });

  it("says the strategy rolls back to the reverted message", () => {
    render(
      <BranchOrRevertDialog
        open
        canBranch
        pending={false}
        error={null}
        onBranch={vi.fn()}
        onRevert={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(
      screen.getByText(
        /The strategy goes back to what it was at this message; a later version stays in your VEuPathDB account\. Saved gene sets are kept\./,
      ),
    ).toBeInTheDocument();
  });

  it("shows no error line when there is no error", () => {
    render(
      <BranchOrRevertDialog
        open
        canBranch
        pending={false}
        error={null}
        onBranch={vi.fn()}
        onRevert={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("edit-dialog-error")).not.toBeInTheDocument();
  });
});
