// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

vi.mock("@/lib/api/privacy", () => ({
  PRIVACY_QUERY_KEY: ["me", "privacy"],
  getPrivacySettings: vi.fn(),
  updatePrivacySettings: vi.fn(),
}));

import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { getPrivacySettings, updatePrivacySettings } from "@/lib/api/privacy";
import { PrivacySettings } from "./PrivacySettings";

const mockedGet = vi.mocked(getPrivacySettings);

function settings(evalDataConsent: boolean) {
  return { evalDataConsent, dataNoticeSeen: "2026-10-09", noticeDue: false };
}
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
  it("states what learning allows, what a shared copy never carries and what turning off does", async () => {
    mockedGet.mockResolvedValue(settings(true));

    render(<PrivacySettings />);

    expect(
      await screen.findByRole("switch", {
        name: "Let PathFinder learn from my strategies",
      }),
    ).toBeChecked();
    expect(screen.getByTestId("privacy-learning-copy")).toHaveTextContent(
      "PathFinder may use copies of your conversations and strategies to improve it for everyone. A copy used beyond review never carries your name or account. Turning this off deletes the copies waiting for review.",
    );
    expect(
      screen.getByRole("link", { name: "Your data in PathFinder" }),
    ).toHaveAttribute("href", "/help/your-data#learning");
  });

  it("shows the toggle on for a consenting account", async () => {
    mockedGet.mockResolvedValue(settings(true));

    render(<PrivacySettings />);

    const toggle = await screen.findByRole("switch", {
      name: "Let PathFinder learn from my strategies",
    });
    expect(toggle).toBeChecked();
  });

  it("shows the toggle off for an account that opted out", async () => {
    mockedGet.mockResolvedValue(settings(false));

    render(<PrivacySettings />);

    expect(
      await screen.findByRole("switch", {
        name: "Let PathFinder learn from my strategies",
      }),
    ).not.toBeChecked();
  });

  it("turns consent off and reflects the server answer", async () => {
    mockedGet.mockResolvedValue(settings(true));
    mockedUpdate.mockResolvedValue(settings(false));

    render(<PrivacySettings />);
    fireEvent.click(
      await screen.findByRole("switch", {
        name: "Let PathFinder learn from my strategies",
      }),
    );

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalledWith({ evalDataConsent: false });
    });
    await waitFor(() => {
      expect(screen.getByRole("switch")).not.toBeChecked();
    });
  });

  it("turns consent back on", async () => {
    mockedGet.mockResolvedValue(settings(false));
    mockedUpdate.mockResolvedValue(settings(true));

    render(<PrivacySettings />);
    fireEvent.click(
      await screen.findByRole("switch", {
        name: "Let PathFinder learn from my strategies",
      }),
    );

    await waitFor(() => {
      expect(mockedUpdate).toHaveBeenCalledWith({ evalDataConsent: true });
    });
    await waitFor(() => {
      expect(screen.getByRole("switch")).toBeChecked();
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
    mockedGet.mockResolvedValue(settings(true));
    mockedUpdate.mockRejectedValue(new Error("nope"));

    render(<PrivacySettings />);
    fireEvent.click(
      await screen.findByRole("switch", {
        name: "Let PathFinder learn from my strategies",
      }),
    );

    expect(await screen.findByText(/Failed to save/i)).toBeVisible();
  });
});
