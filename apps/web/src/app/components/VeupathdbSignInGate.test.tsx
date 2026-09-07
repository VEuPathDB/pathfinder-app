/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { APIError } from "@/lib/api/http";
import { handleWdkAuthRefusal, useAuthGateStore } from "@/state/useAuthGateStore";

import { VeupathdbSignInGate } from "./VeupathdbSignInGate";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

const LOGIN_REQUIRED_BODY = {
  type: "about:blank",
  title: "VEuPathDB login required",
  status: 401,
  detail: "Sign in to VEuPathDB to use searches, strategies and gene sets.",
  code: "WDK_LOGIN_REQUIRED",
};

function renderGate(forced: boolean) {
  return render(
    <VeupathdbSignInGate
      forced={forced}
      selectedSite="plasmodb"
      onSiteChange={vi.fn()}
    />,
  );
}

beforeEach(() => {
  useAuthGateStore.getState().dismissSignIn();
});

describe("VeupathdbSignInGate", () => {
  it("shows an undismissable prompt when the session has no VEuPathDB login", () => {
    renderGate(true);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
  });

  it("shows nothing while the session is signed in and nothing was refused", () => {
    const { baseElement } = renderGate(false);
    expect(baseElement.querySelectorAll("[role='dialog']")).toHaveLength(0);
  });

  it("opens the prompt with the server detail once a refusal set the request", async () => {
    renderGate(false);

    handleWdkAuthRefusal(
      new APIError(LOGIN_REQUIRED_BODY.detail, {
        status: 401,
        statusText: "Unauthorized",
        url: "/api/v1/gene-sets",
        data: LOGIN_REQUIRED_BODY,
      }),
      vi.fn(),
    );

    await waitFor(() => {
      expect(screen.getByText(LOGIN_REQUIRED_BODY.detail)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
