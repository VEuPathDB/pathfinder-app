/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { QuotaResponse } from "@pathfinder/shared/generated/types/QuotaResponse";

import { TooltipProvider } from "@/components/ui/tooltip";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { createTestWrapper } from "@/lib/query/testing";

import { server } from "../../../vitest.msw-setup";
import { RailQuotaMeter, meterTone } from "./RailQuotaMeter";

const SITE = "plasmodb";

const QUOTA: QuotaResponse = {
  usedUsd: "1.25",
  limitUsd: "10.00",
  totalTokens: 123456,
  percent: 12.5,
  resetsAt: "2026-10-01T12:00:00Z",
  ownKeyUsd: "0",
  ownKeyTokens: 0,
  ownKeyProviders: [],
};

const OWN_KEY_QUOTA: QuotaResponse = {
  ...QUOTA,
  ownKeyUsd: "3.40",
  ownKeyTokens: 1_200_000,
  ownKeyProviders: ["openai"],
};

const quotaReads: string[] = [];

beforeEach(() => {
  quotaReads.length = 0;
});

function renderMeter(quota: Partial<QuotaResponse> = {}, signedIn = true) {
  server.use(
    http.get("http://localhost:3000/pathfinder/api/v1/me/quota", ({ request }) => {
      quotaReads.push(request.url);
      return HttpResponse.json({ ...QUOTA, ...quota });
    }),
  );
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(authStatusOptions(SITE).queryKey, { signedIn });
  return render(
    <TooltipProvider>
      <RailQuotaMeter siteId={SITE} />
    </TooltipProvider>,
    { wrapper: Wrapper },
  );
}

async function hoverFigures(): Promise<HTMLElement> {
  await userEvent.hover(await screen.findByRole("img", { name: "Monthly spend" }));
  return await screen.findByRole("tooltip");
}

describe("meterTone", () => {
  it.each([
    [0.5, "neutral"],
    [0.8, "warning"],
    [1, "exhausted"],
  ])("tones %s as %s", (pct, tone) => {
    expect(meterTone(pct)).toBe(tone);
  });
});

describe("RailQuotaMeter", () => {
  it("shows the figures on hover", async () => {
    renderMeter({
      usedUsd: "3.20",
      limitUsd: "10.00",
      totalTokens: 120000,
      resetsAt: "2026-11-01T12:00:00Z",
      ownKeyProviders: [],
    });
    const figures = await hoverFigures();
    expect(within(figures).getByText("$3.20 of $10.00 this month")).toBeVisible();
    expect(within(figures).getByText("120K tokens, resets Nov 1")).toBeVisible();
  });

  it("shows the figures on a touch tap", async () => {
    renderMeter({ usedUsd: "3.20", limitUsd: "10.00" });
    const meter = await screen.findByRole("img", { name: "Monthly spend" });

    await userEvent.pointer({ keys: "[TouchA]", target: meter });

    const figures = await screen.findByRole("tooltip");
    expect(within(figures).getByText("$3.20 of $10.00 this month")).toBeVisible();
  });

  it("shows the account's spend against its monthly limit", async () => {
    renderMeter();
    const figures = await hoverFigures();
    expect(figures).toHaveTextContent("$1.25 of $10.00 this month");
    expect(figures).not.toHaveTextContent("On your keys");
  });

  it("is keyboard reachable and names the account-month scope in its tooltip", async () => {
    renderMeter();
    const meter = await screen.findByRole("img", { name: "Monthly spend" });
    expect(meter).toHaveAttribute("tabindex", "0");

    await userEvent.tab();
    expect(meter).toHaveFocus();
    const figures = await screen.findByRole("tooltip");
    expect(figures).toHaveTextContent(
      "Account total this month, across all conversations.",
    );
    expect(figures).toHaveTextContent("123.5K tokens, resets Oct 1");
  });

  it("adds the spend on the researcher's keys to the allowance figures", async () => {
    renderMeter(OWN_KEY_QUOTA);
    const figures = await hoverFigures();
    expect(
      within(figures).getByText("On your keys this month: $3.40, 1.2M tokens"),
    ).toBeVisible();
    expect(figures).toHaveTextContent("$1.25 of $10.00 this month");
    expect(screen.getByTestId("quota-ring-fill")).toHaveAttribute(
      "stroke-dasharray",
      "12.5 100",
    );
  });

  it("fills the ring to the share of the allowance spent", async () => {
    renderMeter();
    await screen.findByRole("img", { name: "Monthly spend" });
    const fill = screen.getByTestId("quota-ring-fill");
    expect(fill).toHaveAttribute("stroke-dasharray", "12.5 100");
    expect(fill).toHaveClass("stroke-primary");
  });

  it("turns amber at 80 percent of the allowance", async () => {
    renderMeter({ usedUsd: "8.50" });
    await screen.findByRole("img", { name: "Monthly spend" });
    const fill = screen.getByTestId("quota-ring-fill");
    expect(fill).toHaveAttribute("stroke-dasharray", "85 100");
    expect(fill).toHaveClass("stroke-warning");
  });

  it("turns red and stays full past the allowance", async () => {
    renderMeter({ usedUsd: "12.00" });
    await screen.findByRole("img", { name: "Monthly spend" });
    const fill = screen.getByTestId("quota-ring-fill");
    expect(fill).toHaveAttribute("stroke-dasharray", "100 100");
    expect(fill).toHaveClass("stroke-destructive");
  });

  it("leaves a refused sign-in status for the shell to read again", async () => {
    const statusReads: string[] = [];
    server.use(
      http.get(
        "http://localhost:3000/pathfinder/api/v1/veupathdb/auth/status",
        ({ request }) => {
          statusReads.push(request.url);
          return HttpResponse.json(
            { title: "Cannot reach the site", status: 503, code: "SITE_UNAVAILABLE" },
            { status: 503 },
          );
        },
      ),
    );
    const { queryClient, Wrapper } = createTestWrapper();
    await queryClient.prefetchQuery(authStatusOptions(SITE));
    expect(statusReads).toHaveLength(1);

    render(
      <TooltipProvider>
        <RailQuotaMeter siteId={SITE} />
      </TooltipProvider>,
      { wrapper: Wrapper },
    );

    await waitFor(() =>
      expect(
        queryClient.getQueryState(authStatusOptions(SITE).queryKey)?.fetchStatus,
      ).toBe("idle"),
    );
    expect(statusReads).toHaveLength(1);
    expect(screen.queryByRole("img", { name: "Monthly spend" })).toBeNull();
  });

  it("asks for no quota while the reader is signed out", async () => {
    renderMeter({}, false);

    await waitFor(() =>
      expect(screen.queryByRole("img", { name: "Monthly spend" })).toBeNull(),
    );
    expect(quotaReads).toEqual([]);
  });
});
