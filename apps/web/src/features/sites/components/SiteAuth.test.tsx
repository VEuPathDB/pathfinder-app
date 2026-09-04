/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";

import { SiteAuth } from "./SiteAuth";
import { logoutVeupathdb } from "@/lib/api/veupathdb-auth";

interface AuthStatus {
  signedIn: boolean;
  name?: string | null;
}

const AUTH_KEY = (site: string): readonly unknown[] => ["veupathdb-auth", site];

vi.mock("@/lib/api/veupathdb-auth", () => ({
  authStatusOptions: (site: string) => ({
    queryKey: ["veupathdb-auth", site],
    queryFn: () => Promise.resolve({ signedIn: false }),
  }),
  logoutVeupathdb: vi.fn(() => Promise.resolve({ success: true })),
}));

vi.mock("@/features/sites/useHasHydrated", () => ({ useHasHydrated: () => true }));
vi.mock("@/lib/query/invalidateUserScoped", () => ({
  invalidateUserScopedQueries: vi.fn(),
}));

const mockLogout = vi.mocked(logoutVeupathdb);

function renderAuth(
  status: AuthStatus,
  props: { authDisplay?: "button" | "inline" } = {},
): QueryClient {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
    },
  });
  qc.setQueryData(AUTH_KEY("plasmodb"), status);
  const ui: ReactElement = (
    <QueryClientProvider client={qc}>
      <SiteAuth siteId="plasmodb" {...props} />
    </QueryClientProvider>
  );
  render(ui);
  return qc;
}

afterEach(cleanup);
beforeEach(() => mockLogout.mockClear());

describe("SiteAuth", () => {
  it("greets the signed-in user by name and logs out on click", async () => {
    renderAuth({ signedIn: true, name: "Dr. Rivera" });

    expect(screen.getByText("Logged in as Dr. Rivera")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /log out/i }));
    await waitFor(() => expect(mockLogout.mock.calls).toEqual([["plasmodb"]]));
  });

  it("shows an em-dash when the signed-in user has no name", () => {
    renderAuth({ signedIn: true, name: null });
    expect(screen.getByText(/^Logged in as/)).toHaveTextContent("Logged in as —");
  });

  it("offers the 'Sign in →' affordance when signed out", () => {
    renderAuth({ signedIn: false });
    const button = screen.getByRole("button", { name: /sign in/i });
    expect(button).toHaveTextContent("Sign in →");
  });

  it("renders the inline sign-in form when signed out in inline mode", () => {
    renderAuth({ signedIn: false }, { authDisplay: "inline" });
    expect(screen.getByPlaceholderText("Email")).toHaveValue("");
    expect(screen.getByPlaceholderText("Password")).toHaveValue("");
  });
});
