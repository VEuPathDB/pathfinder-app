/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/veupathdb/conversation",
  useSearchParams: () => new URLSearchParams("step=4"),
}));

const goToSiteSignIn = vi.hoisted(() => vi.fn());
vi.mock("@/lib/siteSignIn", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  goToSiteSignIn,
}));

import { SITE_SIGN_IN_URL, renderWithConfig } from "./__fixtures__/renderWithConfig";
import { SignedOutNotice } from "./SignedOutNotice";

beforeEach(() => goToSiteSignIn.mockClear());
afterEach(cleanup);

function signInLink(): HTMLElement {
  return screen.getByRole("link", { name: "Sign in to VEuPathDB" });
}

function clickKeepsDefault(init: MouseEventInit = {}): boolean {
  let kept = false;
  const record = (event: Event) => {
    kept = !event.defaultPrevented;
    event.preventDefault();
  };
  document.addEventListener("click", record);
  fireEvent.click(signInLink(), init);
  document.removeEventListener("click", record);
  return kept;
}

describe("SignedOutNotice", () => {
  it("renders the reason and the sign-in link", () => {
    renderWithConfig(
      <SignedOutNotice reason="Sign in to VEuPathDB to use searches." />,
    );
    expect(screen.getByText("Sign in to VEuPathDB to use searches.")).toBeVisible();
    expect(signInLink()).toHaveAttribute(
      "href",
      expect.stringContaining("/app/user/login?destination="),
    );
  });

  it("shows the standing text when no reason is given", () => {
    renderWithConfig(<SignedOutNotice />);
    expect(
      screen.getByText("Sign in to VEuPathDB to build and manage search strategies."),
    ).toBeVisible();
  });

  it("links to the website login with this page under the base path", () => {
    renderWithConfig(<SignedOutNotice reason={null} />);
    expect(signInLink()).toHaveAttribute(
      "href",
      `${SITE_SIGN_IN_URL}?destination=${encodeURIComponent(
        "/pathfinder/veupathdb/conversation?step=4",
      )}`,
    );
    expect(signInLink()).toHaveAttribute("target", "_top");
  });

  it("sends a click to the website login through the page that shows PathFinder", () => {
    renderWithConfig(<SignedOutNotice />);

    expect(clickKeepsDefault()).toBe(false);
    expect(goToSiteSignIn.mock.calls).toEqual([[window, SITE_SIGN_IN_URL]]);
  });

  it("leaves a click that opens a new tab to the browser", () => {
    renderWithConfig(<SignedOutNotice />);

    expect(clickKeepsDefault({ ctrlKey: true })).toBe(true);
    expect(goToSiteSignIn).not.toHaveBeenCalled();
  });

  it("names PathFinder and offers no password field", () => {
    const { container } = renderWithConfig(<SignedOutNotice />);
    expect(screen.getByText("PathFinder")).toBeVisible();
    expect(container.querySelectorAll("input")).toHaveLength(0);
  });
});
