/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { APIError } from "@/lib/api/http";
import { handleWdkAuthRefusal, useAuthGateStore } from "@/state/useAuthGateStore";

import { renderWithConfig } from "./__fixtures__/renderWithConfig";
import { VeupathdbSignInGate } from "./VeupathdbSignInGate";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/plasmodb/conversation",
  useSearchParams: () => new URLSearchParams(),
}));

const LOGIN_REQUIRED_BODY = {
  type: "about:blank",
  title: "VEuPathDB login required",
  status: 401,
  detail:
    "VEuPathDB serves registered users only, and this request carried no registered VEuPathDB token.",
  code: "WDK_LOGIN_REQUIRED",
};

beforeEach(() => {
  useAuthGateStore.getState().dismissSignIn();
});

describe("VeupathdbSignInGate", () => {
  it("takes the whole screen with the website's sign-in link when the session is signed out", () => {
    renderWithConfig(<VeupathdbSignInGate forced />);
    const region = screen.getByRole("region", { name: "Sign in to VEuPathDB" });
    expect(region).toContainElement(screen.getByTestId("signed-out-notice"));
    expect(
      screen.getByRole("heading", { level: 1, name: "Sign in to VEuPathDB" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to VEuPathDB" })).toHaveAttribute(
      "href",
      expect.stringContaining("/app/user/login?destination="),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });

  it("shows nothing while the session is signed in and nothing was refused", () => {
    const { baseElement } = renderWithConfig(<VeupathdbSignInGate forced={false} />);
    expect(baseElement.querySelectorAll("[role='dialog']")).toHaveLength(0);
    expect(screen.queryByTestId("signed-out-notice")).not.toBeInTheDocument();
  });

  it("opens a dismissible notice with the server detail once a refusal set the request", async () => {
    renderWithConfig(<VeupathdbSignInGate forced={false} />);

    handleWdkAuthRefusal(
      new APIError(LOGIN_REQUIRED_BODY.detail, {
        status: 401,
        statusText: "Unauthorized",
        url: "/api/v1/gene-sets",
        data: LOGIN_REQUIRED_BODY,
      }),
      vi.fn(),
    );

    const dialog = await screen.findByRole("dialog", { name: "Sign in to VEuPathDB" });
    expect(dialog).toHaveTextContent(LOGIN_REQUIRED_BODY.detail);
    expect(screen.getByRole("link", { name: "Sign in to VEuPathDB" })).toHaveAttribute(
      "href",
      expect.stringContaining("/app/user/login?destination="),
    );

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(useAuthGateStore.getState().signInRequired).toBe(false);
  });
});
