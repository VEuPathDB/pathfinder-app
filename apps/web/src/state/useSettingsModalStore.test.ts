import { afterEach, describe, expect, it } from "vitest";

import { useSettingsModalStore } from "./useSettingsModalStore";

afterEach(() => {
  useSettingsModalStore.setState({ isOpen: false, tab: "model" });
});

describe("useSettingsModalStore", () => {
  it("starts closed on the model tab", () => {
    expect(useSettingsModalStore.getState()).toMatchObject({
      isOpen: false,
      tab: "model",
    });
  });

  it("opens on the tab a caller names", () => {
    useSettingsModalStore.getState().open("keys");
    expect(useSettingsModalStore.getState()).toMatchObject({
      isOpen: true,
      tab: "keys",
    });
  });

  it("opens on the last tab when the caller names none", () => {
    useSettingsModalStore.getState().setTab("privacy");
    useSettingsModalStore.getState().open();
    expect(useSettingsModalStore.getState()).toMatchObject({
      isOpen: true,
      tab: "privacy",
    });
  });

  it("closes and keeps the tab", () => {
    useSettingsModalStore.getState().open("data");
    useSettingsModalStore.getState().close();
    expect(useSettingsModalStore.getState()).toMatchObject({
      isOpen: false,
      tab: "data",
    });
  });
});
