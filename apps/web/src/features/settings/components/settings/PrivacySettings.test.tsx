// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

vi.mock("@/features/settings/api/privacy", () => ({
  getPrivacySettings: vi.fn(),
  updatePrivacySettings: vi.fn(),
}));

import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import {
  getPrivacySettings,
  updatePrivacySettings,
} from "@/features/settings/api/privacy";
import { PrivacySettings } from "./PrivacySettings";

const mockedGet = vi.mocked(getPrivacySettings);
const mockedUpdate = vi.mocked(updatePrivacySettings);

beforeEach(() => {
  mockedGet.mockReset();
  mockedUpdate.mockReset();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PrivacySettings", () => {
  it("shows the toggle on for a consenting account", async () => {
    mockedGet.mockResolvedValue({ evalDataConsent: true, noticeSeen: true });

    render(<PrivacySettings />);

    const toggle = await screen.findByRole("checkbox");
    expect(toggle).toBeChecked();
  });

  it("shows the toggle off for an account that opted out", async () => {
    mockedGet.mockResolvedValue({ evalDataConsent: false, noticeSeen: true });

    render(<PrivacySettings />);

    expect(await screen.findByRole("checkbox")).not.toBeChecked();
  });

  it("turns consent off and reflects the server answer", async () => {
    mockedGet.mockResolvedValue({ evalDataConsent: true, noticeSeen: true });
    mockedUpdate.mockResolvedValue({ evalDataConsent: false, noticeSeen: true });

    render(<PrivacySettings />);
    fireEvent.click(await screen.findByRole("checkbox"));

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalledWith({ evalDataConsent: false });
    });
    await waitFor(() => {
      expect(screen.getByRole("checkbox")).not.toBeChecked();
    });
  });

  it("turns consent back on", async () => {
    mockedGet.mockResolvedValue({ evalDataConsent: false, noticeSeen: true });
    mockedUpdate.mockResolvedValue({ evalDataConsent: true, noticeSeen: true });

    render(<PrivacySettings />);
    fireEvent.click(await screen.findByRole("checkbox"));

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalledWith({ evalDataConsent: true });
    });
    await waitFor(() => {
      expect(screen.getByRole("checkbox")).toBeChecked();
    });
  });

  it("reports a failed load", async () => {
    mockedGet.mockRejectedValue(new Error("boom"));

    render(<PrivacySettings />);

    expect(await screen.findByText(/Failed to load privacy settings/i)).toBeVisible();
  });

  it("reports a failed load once, with no toast", async () => {
    mockedGet.mockRejectedValue(new Error("privacy read failed"));

    render(<PrivacySettings />, { wrapper: appQueryClientWrapper() });

    expect(
      await screen.findByText("Failed to load privacy settings: privacy read failed"),
    ).toBeVisible();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("reports a failed save", async () => {
    mockedGet.mockResolvedValue({ evalDataConsent: true, noticeSeen: true });
    mockedUpdate.mockRejectedValue(new Error("nope"));

    render(<PrivacySettings />);
    fireEvent.click(await screen.findByRole("checkbox"));

    expect(await screen.findByText(/Failed to save/i)).toBeVisible();
  });
});
