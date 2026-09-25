/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactElement } from "react";

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
vi.mock("./settings/SeedingSettings", () => ({
  SeedingSettings: () => <p>Seeding body</p>,
}));

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

function selectedTab(): string {
  return screen.getByRole("tab", { selected: true }).textContent;
}

afterEach(cleanup);

describe("SettingsPage tabs", () => {
  it("names the tabs in a tablist and ties the selected one to its panel", () => {
    render(<Harness initial="data" />);

    const tabs = screen.getAllByRole("tab");
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Model",
      "Provider keys",
      "Data",
      "Memory",
      "Privacy",
      "Advanced",
      "Seeding",
    ]);
    const data = screen.getByRole("tab", { name: "Data" });
    expect(data).toHaveAttribute("aria-selected", "true");
    const panel = screen.getByRole("tabpanel");
    expect(data.getAttribute("aria-controls")).toBe(panel.id);
    expect(panel.getAttribute("aria-labelledby")).toBe(data.id);
    expect(panel).toHaveTextContent("Data body");
  });

  it("takes one Tab stop, which lands on the selected tab", async () => {
    render(<Harness initial="data" />);

    screen.getByRole("button", { name: "Close" }).focus();
    await userEvent.tab();

    const data = screen.getByRole("tab", { name: "Data" });
    expect(document.activeElement).toBe(data);
    expect(screen.getAllByRole("tab").map((t) => t.tabIndex)).toEqual([
      -1, -1, 0, -1, -1, -1, -1,
    ]);
  });

  it("moves with the arrow keys and wraps at the ends", async () => {
    render(<Harness initial="model" />);

    screen.getByRole("tab", { name: "Model" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(selectedTab()).toBe("Provider keys");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Keys body");
    expect(document.activeElement).toBe(
      screen.getByRole("tab", { name: "Provider keys" }),
    );

    await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(selectedTab()).toBe("Seeding");
  });

  it("jumps to the first and the last tab with Home and End", async () => {
    render(<Harness initial="memory" />);

    screen.getByRole("tab", { name: "Memory" }).focus();
    await userEvent.keyboard("{End}");
    expect(selectedTab()).toBe("Seeding");

    await userEvent.keyboard("{Home}");
    expect(selectedTab()).toBe("Model");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Model body");
  });
});
