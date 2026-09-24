// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { useSessionStore } from "@/state/useSessionStore";
import { server } from "../../../../../vitest.msw-setup";
import { StrategyTab } from "./DatasetParamTabs";

beforeEach(() => {
  toastError.mockClear();
  useSessionStore.getState().setSelectedSite("plasmodb");
});
afterEach(cleanup);

describe("StrategyTab", () => {
  it("reports a failed strategy list once, inline and not as a toast", async () => {
    server.use(
      http.get("*/api/v1/conversations", () =>
        HttpResponse.json({ detail: "upstream is down" }, { status: 502 }),
      ),
    );

    render(<StrategyTab value="" onChange={vi.fn()} />, {
      wrapper: appQueryClientWrapper(),
    });

    expect(
      await screen.findByText("Couldn't load strategies for this site."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Couldn't load strategies for this site.")).toHaveLength(
      1,
    );
    expect(toastError).not.toHaveBeenCalled();
  });
});
