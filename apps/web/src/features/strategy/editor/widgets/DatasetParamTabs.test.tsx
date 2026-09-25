// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { useSessionStore } from "@/state/useSessionStore";
import { server } from "../../../../../vitest.msw-setup";
import { PasteTab, StrategyTab } from "./DatasetParamTabs";

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

  it("offers the strategies the site holds, by their WDK strategy id", async () => {
    server.use(
      http.get("*/api/v1/conversations", () =>
        HttpResponse.json([
          {
            id: "5b0c1d2e-0000-4000-8000-000000000001",
            name: "Kinases",
            siteId: "plasmodb",
            recordType: "transcript",
            createdAt: "2026-09-24T00:00:00Z",
            updatedAt: "2026-09-24T00:00:00Z",
            wdkStrategyId: 330713643,
          },
          {
            id: "5b0c1d2e-0000-4000-8000-000000000002",
            name: "Draft",
            siteId: "plasmodb",
            recordType: "transcript",
            createdAt: "2026-09-24T00:00:00Z",
            updatedAt: "2026-09-24T00:00:00Z",
            wdkStrategyId: null,
          },
        ]),
      ),
    );
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(<StrategyTab value="" onChange={onChange} />, {
      wrapper: appQueryClientWrapper(),
    });
    await user.click(await screen.findByRole("combobox"));
    await user.click(await screen.findByText("Kinases"));

    expect(screen.queryByText("Draft")).toBeNull();
    expect(onChange.mock.calls).toEqual([["330713643"]]);
  });
});

describe("PasteTab", () => {
  it("says what the site does with the IDs, not the source type", () => {
    render(
      <PasteTab
        text={"PF3D7_1133400\nPF3D7_0709000"}
        onTextChange={vi.fn()}
        name="ds"
      />,
    );

    expect(screen.getByText("2 IDs")).toBeVisible();
    expect(screen.getByText("The site saves these IDs as a new list.")).toBeVisible();
    expect(screen.queryByText(/idList/)).toBeNull();
  });
});
