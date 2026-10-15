/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useQuery } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { TooltipProvider } from "@/components/ui/tooltip";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";
import { server } from "../../../vitest.msw-setup";
import { RailSignOut } from "./RailSignOut";

const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast: { error: toastError } }));

afterEach(cleanup);

function SignInStatus() {
  const { data } = useQuery(authStatusOptions("plasmodb"));
  return <output>{data?.signedIn === true ? "signed in" : "signed out"}</output>;
}

function draw() {
  const { Wrapper } = createTestWrapper();
  render(
    <Wrapper>
      <TooltipProvider>
        <SignInStatus />
        <RailSignOut siteId="plasmodb" />
      </TooltipProvider>
    </Wrapper>,
  );
}

describe("RailSignOut", () => {
  it("signs out on the site and reads the sign-in status again", async () => {
    const signedOutOn: string[] = [];
    server.use(
      http.post("*/api/v1/veupathdb/auth/logout", ({ request }) => {
        signedOutOn.push(new URL(request.url).searchParams.get("siteId") ?? "");
        return HttpResponse.json({ success: true });
      }),
      http.get("*/api/v1/veupathdb/auth/status", () =>
        HttpResponse.json({ signedIn: signedOutOn.length === 0 }),
      ),
    );
    draw();
    expect(await screen.findByText("signed in")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByText("signed out")).toBeVisible();
    expect(signedOutOn).toEqual(["plasmodb"]);
  });

  it("says so when the sign-out fails", async () => {
    server.use(
      http.post("*/api/v1/veupathdb/auth/logout", () =>
        HttpResponse.json(
          { title: "Error", status: 500, detail: "boom", code: "INTERNAL" },
          { status: 500 },
        ),
      ),
    );
    draw();

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await vi.waitFor(() => expect(toastError).toHaveBeenCalledOnce());
    expect(toastError.mock.calls[0]?.[0]).toMatch(/^Sign-out failed: /);
  });
});
