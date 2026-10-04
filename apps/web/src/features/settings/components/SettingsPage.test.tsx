/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactElement } from "react";
import { healthCheckQueryKey } from "@pathfinder/shared/generated/hooks/useHealthCheck";

import { createTestWrapper } from "@/lib/query/testing";
import type { SettingsTab } from "../types";
import { SettingsPage } from "./SettingsPage";

vi.mock("./settings/ModelSettings", () => ({ ModelSettings: () => <p>Model body</p> }));
vi.mock("./settings/ProviderKeySettings", () => ({
  ProviderKeySettings: () => <p>Keys body</p>,
}));
vi.mock("./settings/DataSettings", () => ({ DataSettings: () => <p>Data body</p> }));
vi.mock("./settings/MemorySettings", () => ({
  MemorySettings: () => <p>Memory body</p>,
}));
vi.mock("./settings/PrivacySettings", () => ({
  PrivacySettings: () => <p>Privacy body</p>,
}));
vi.mock("./settings/AdvancedSettings", () => ({
  AdvancedSettings: () => <p>Advanced body</p>,
}));

const HEALTH = {
  status: "healthy",
  version: "0.2.0a23",
  timestamp: "2026-10-04T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function Harness({ initial }: { initial: SettingsTab }): ReactElement {
  const [tab, setTab] = useState<SettingsTab>(initial);
  return (
    <SettingsPage
      open
      onClose={vi.fn()}
      siteId="plasmodb"
      tab={tab}
      onTabChange={setTab}
    />
  );
}

function renderSettings(initial: SettingsTab) {
  const { queryClient, Wrapper } = createTestWrapper();
  render(
    <Wrapper>
      <Harness initial={initial} />
    </Wrapper>,
  );
  return queryClient;
}

function selectedTab(): string {
  return screen.getByRole("tab", { selected: true }).textContent;
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse(HEALTH)),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SettingsPage tabs", () => {
  it("names the tabs in a tablist and ties the selected one to its panel", () => {
    renderSettings("data");

    const tabs = screen.getAllByRole("tab");
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Model",
      "Provider keys",
      "Data",
      "Memory",
      "Privacy",
      "Advanced",
    ]);
    const data = screen.getByRole("tab", { name: "Data" });
    expect(data).toHaveAttribute("aria-selected", "true");
    const panel = screen.getByRole("tabpanel");
    expect(data.getAttribute("aria-controls")).toBe(panel.id);
    expect(panel.getAttribute("aria-labelledby")).toBe(data.id);
    expect(panel).toHaveTextContent("Data body");
  });

  it("takes one Tab stop, which lands on the selected tab", async () => {
    renderSettings("data");

    screen.getByRole("button", { name: "Close" }).focus();
    await userEvent.tab();

    const data = screen.getByRole("tab", { name: "Data" });
    expect(document.activeElement).toBe(data);
    expect(screen.getAllByRole("tab").map((t) => t.tabIndex)).toEqual([
      -1, -1, 0, -1, -1, -1,
    ]);
  });

  it("moves with the arrow keys and wraps at the ends", async () => {
    renderSettings("model");

    screen.getByRole("tab", { name: "Model" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(selectedTab()).toBe("Provider keys");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Keys body");
    expect(document.activeElement).toBe(
      screen.getByRole("tab", { name: "Provider keys" }),
    );

    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(selectedTab()).toBe("Advanced");
  });

  it("jumps to the first and the last tab with Home and End", async () => {
    renderSettings("memory");

    screen.getByRole("tab", { name: "Memory" }).focus();
    await userEvent.keyboard("{End}");
    expect(selectedTab()).toBe("Advanced");

    await userEvent.keyboard("{Home}");
    expect(selectedTab()).toBe("Model");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Model body");
  });
});

describe("SettingsPage release", () => {
  it("names the release the api reports, under every tab", async () => {
    renderSettings("model");

    const release = await screen.findByTestId("settings-release");
    expect(release.textContent).toBe("PathFinder v0.2.0a23");
    expect(screen.getByRole("tabpanel")).not.toContainElement(release);

    await userEvent.click(screen.getByRole("tab", { name: "Privacy" }));
    expect(screen.getByTestId("settings-release")).toHaveTextContent(
      "PathFinder v0.2.0a23",
    );
  });

  it("shows no release until the api answers", async () => {
    let answer: (response: Response) => void = () => {};
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          answer = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderSettings("model");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("settings-release")).not.toBeInTheDocument();

    answer(jsonResponse(HEALTH));
    expect((await screen.findByTestId("settings-release")).textContent).toBe(
      "PathFinder v0.2.0a23",
    );
  });

  it("shows no release when the api call fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "down" }, 500)),
    );
    const queryClient = renderSettings("model");

    await waitFor(() =>
      expect(queryClient.getQueryState(healthCheckQueryKey())?.status).toBe("error"),
    );
    expect(screen.queryByTestId("settings-release")).not.toBeInTheDocument();
  });
});
