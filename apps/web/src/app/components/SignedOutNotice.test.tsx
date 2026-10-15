/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { getVeupathdbAuthStatus, loginVeupathdb } from "@/lib/api/veupathdb-auth";
import { useAuthGateStore } from "@/state/useAuthGateStore";
import { renderWithConfig } from "./__fixtures__/renderWithConfig";
import { SignedOutNotice } from "./SignedOutNotice";

vi.mock("@/lib/api/veupathdb-auth", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  loginVeupathdb: vi.fn(),
  getVeupathdbAuthStatus: vi.fn(),
}));

afterEach(cleanup);

describe("SignedOutNotice", () => {
  it("renders the reason", () => {
    renderWithConfig(
      <SignedOutNotice reason="Sign in to VEuPathDB to use searches." />,
    );
    expect(screen.getByText("Sign in to VEuPathDB to use searches.")).toBeVisible();
  });

  it("shows the standing text when no reason is given", () => {
    renderWithConfig(<SignedOutNotice />);
    expect(
      screen.getByText("Sign in to VEuPathDB to build and manage search strategies."),
    ).toBeVisible();
  });

  it("names PathFinder and asks for the VEuPathDB email and password", () => {
    renderWithConfig(<SignedOutNotice />);
    expect(screen.getByText("PathFinder")).toBeVisible();
    expect(screen.getByPlaceholderText("Email")).toHaveAttribute("type", "email");
    expect(screen.getByPlaceholderText("Password")).toHaveAttribute("type", "password");
  });

  it("closes the prompt once the sign-in succeeds", async () => {
    vi.mocked(loginVeupathdb).mockResolvedValue({ success: true });
    vi.mocked(getVeupathdbAuthStatus).mockResolvedValue({ signedIn: true });
    useAuthGateStore.getState().requestSignIn("Sign in to VEuPathDB to use searches.");
    renderWithConfig(<SignedOutNotice />);

    await userEvent.type(
      screen.getByPlaceholderText("Email"),
      "researcher@example.org",
    );
    await userEvent.type(screen.getByPlaceholderText("Password"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await vi.waitFor(() =>
      expect(useAuthGateStore.getState().signInRequired).toBe(false),
    );
    expect(vi.mocked(loginVeupathdb).mock.calls).toEqual([
      ["researcher@example.org", "secret", "veupathdb"],
    ]);
  });

  it("links to the statement of what PathFinder does with your data", () => {
    renderWithConfig(<SignedOutNotice />);
    expect(
      screen.getByRole("link", { name: "Your data in PathFinder" }),
    ).toHaveAttribute("href", "/help/your-data");
  });
});
