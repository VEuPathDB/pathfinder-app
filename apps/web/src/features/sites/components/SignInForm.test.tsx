/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

import { APIError } from "@/lib/api/http";
import { createTestQueryClient } from "@/lib/query/testing";
import { SignInForm } from "./SignInForm";
import { getVeupathdbAuthStatus, loginVeupathdb } from "@/lib/api/veupathdb-auth";

vi.mock("@/lib/api/veupathdb-auth", () => ({
  loginVeupathdb: vi.fn(),
  getVeupathdbAuthStatus: vi.fn(),
  authStatusOptions: (site: string) => ({ queryKey: ["veupathdb-auth", site] }),
}));

vi.mock("@/state/useSessionStore", () => ({
  useSessionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ selectedSite: "plasmodb" }),
}));

const mockLogin = vi.mocked(loginVeupathdb);
const mockStatus = vi.mocked(getVeupathdbAuthStatus);

function renderForm(onSuccess = vi.fn()): { onSuccess: ReturnType<typeof vi.fn> } {
  const ui: ReactElement = (
    <QueryClientProvider client={createTestQueryClient()}>
      <SignInForm onSuccess={onSuccess} />
    </QueryClientProvider>
  );
  render(ui);
  return { onSuccess };
}

async function fillCredentials(email: string, password: string): Promise<void> {
  await userEvent.type(screen.getByPlaceholderText("Email"), email);
  await userEvent.type(screen.getByPlaceholderText("Password"), password);
}

afterEach(cleanup);
beforeEach(() => {
  mockLogin.mockReset();
  mockStatus.mockReset();
});

describe("SignInForm", () => {
  it("logs in with the typed credentials + selected site, then calls onSuccess", async () => {
    mockLogin.mockResolvedValue({ success: true });
    mockStatus.mockResolvedValue({ signedIn: true, name: "Dr. Rivera" });
    const { onSuccess } = renderForm();

    await fillCredentials("ahmed@upenn.edu", "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(mockLogin.mock.calls).toEqual([["ahmed@upenn.edu", "hunter2", "plasmodb"]]);
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("shows a credential error and does not call onSuccess when not signed in", async () => {
    mockLogin.mockResolvedValue({ success: true });
    mockStatus.mockResolvedValue({ signedIn: false });
    const { onSuccess } = renderForm();

    await fillCredentials("ahmed@upenn.edu", "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText("Login failed. Please check your credentials."),
    ).toBeTruthy();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("shows a generic error when the login request throws", async () => {
    mockLogin.mockRejectedValue(new Error("network down"));
    const { onSuccess } = renderForm();

    await fillCredentials("ahmed@upenn.edu", "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Login failed. Please try again.")).toBeTruthy();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("shows the site notice inline when the login reports the site is down", async () => {
    mockLogin.mockRejectedValue(
      new APIError("veupathdb is not responding (ReadTimeout).", {
        status: 503,
        statusText: "Service Unavailable",
        url: "http://localhost:3000/api/v1/veupathdb/auth/login",
        data: {
          type: "/errors/SITE_UNAVAILABLE",
          title: "Site is not responding",
          status: 503,
          detail: "veupathdb is not responding (ReadTimeout).",
          code: "SITE_UNAVAILABLE",
        },
      }),
    );
    const { onSuccess } = renderForm();

    await fillCredentials("ahmed@upenn.edu", "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByTestId("site-unavailable-notice")).toBeTruthy();
    expect(screen.getByText("plasmodb is not responding")).toBeTruthy();
    expect(screen.queryByText("Login failed. Please try again.")).toBeNull();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("submits on Enter in the password field", async () => {
    mockLogin.mockResolvedValue({ success: true });
    mockStatus.mockResolvedValue({ signedIn: true, name: "x" });
    const { onSuccess } = renderForm();

    await fillCredentials("ahmed@upenn.edu", "hunter2");
    await userEvent.type(screen.getByPlaceholderText("Password"), "{Enter}");

    expect(mockLogin).toHaveBeenCalledExactlyOnceWith(
      "ahmed@upenn.edu",
      "hunter2",
      "plasmodb",
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });
});
