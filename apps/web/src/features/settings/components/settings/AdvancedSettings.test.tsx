// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { useSettingsStore } from "@/state/useSettingsStore";
import { AdvancedSettings } from "./AdvancedSettings";

beforeEach(() => useSettingsStore.getState().resetToDefaults());
afterEach(cleanup);

describe("AdvancedSettings", () => {
  it("turns each preference on and off with a switch", () => {
    render(<AdvancedSettings />);

    const before = useSettingsStore.getState();
    for (const name of [
      "Also delete on VEuPathDB",
      "Show token usage",
      "Show raw tool calls",
    ]) {
      fireEvent.click(screen.getByRole("switch", { name }));
    }

    const after = useSettingsStore.getState();
    expect(after.deleteFromWdk).toBe(!before.deleteFromWdk);
    expect(after.showTokenUsage).toBe(!before.showTokenUsage);
    expect(after.showRawToolCalls).toBe(!before.showRawToolCalls);
  });

  it("shows each switch in the state the store holds", () => {
    useSettingsStore.getState().setShowTokenUsage(true);
    render(<AdvancedSettings />);

    expect(screen.getByRole("switch", { name: "Show token usage" })).toBeChecked();
  });

  it("offers the reset of the settings this browser keeps", () => {
    render(<AdvancedSettings />);

    expect(
      screen.getByRole("button", { name: "Reset all local settings" }),
    ).toBeVisible();
  });
});
