// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { DATA_STATEMENT_VERSION, type PrivacySettings } from "@pathfinder/shared";

vi.mock("@/lib/api/privacy", () => ({
  PRIVACY_QUERY_KEY: ["me", "privacy"],
  getPrivacySettings: vi.fn(),
  continuePastDataNotice: vi.fn(),
}));

const authState = { refreshed: true, signedIn: true };

vi.mock("@/lib/query/hooks/useAuthRefresh", () => ({
  useAuthRefresh: () => ({ authRefreshed: authState.refreshed }),
}));

vi.mock("@/lib/api/veupathdb-auth", () => ({
  authStatusOptions: (siteId: string) => ({
    queryKey: ["auth", "status", siteId],
    queryFn: () => ({ signedIn: authState.signedIn }),
  }),
}));

import { continuePastDataNotice, getPrivacySettings } from "@/lib/api/privacy";
import { DataNotice } from "./DataNotice";
import { YOUR_DATA_IN_BRIEF } from "./yourDataBrief";

const mockedGet = vi.mocked(getPrivacySettings);
const mockedContinue = vi.mocked(continuePastDataNotice);

const DUE: PrivacySettings = {
  evalDataConsent: true,
  dataNoticeSeen: null,
  noticeDue: true,
};

function seen(consent: boolean): PrivacySettings {
  return {
    evalDataConsent: consent,
    dataNoticeSeen: DATA_STATEMENT_VERSION,
    noticeDue: false,
  };
}

beforeEach(() => {
  mockedGet.mockReset();
  mockedContinue.mockReset();
  authState.refreshed = true;
  authState.signedIn = true;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("DataNotice", () => {
  it("shows the statement in brief to an account that has not seen this version", async () => {
    mockedGet.mockResolvedValue(DUE);

    render(<DataNotice />);

    const notice = await screen.findByRole("alertdialog", {
      name: "Your data in PathFinder",
    });
    expect([...notice.querySelectorAll("li")].map((item) => item.textContent)).toEqual([
      ...YOUR_DATA_IN_BRIEF,
    ]);
  });

  it("opens the full statement in a new tab", async () => {
    mockedGet.mockResolvedValue(DUE);

    render(<DataNotice />);

    const link = await screen.findByRole("link", { name: "Read the full statement" });
    expect(link).toHaveAttribute("href", "/help/your-data");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("offers learning ticked, with a line that says what it means", async () => {
    mockedGet.mockResolvedValue(DUE);

    render(<DataNotice />);

    const box = await screen.findByRole("checkbox", {
      name: "Let PathFinder learn from my strategies",
    });
    expect(box).toBeChecked();
    expect(box).toHaveAccessibleDescription(
      "Copies of your conversations and strategies may be read by the team and used, without your name or account, to improve PathFinder for everyone. You can change this later in Settings, on the Privacy tab.",
    );
  });

  it("records the version with learning on when the box stays ticked", async () => {
    mockedGet.mockResolvedValue(DUE);
    mockedContinue.mockResolvedValue(seen(true));

    render(<DataNotice />);
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBe(null);
    });
    expect(mockedContinue.mock.calls[0]?.[0]).toBe(true);
  });

  it("records learning off when the box is unticked", async () => {
    mockedGet.mockResolvedValue(DUE);
    mockedContinue.mockResolvedValue(seen(false));

    render(<DataNotice />);
    fireEvent.click(
      await screen.findByRole("checkbox", {
        name: "Let PathFinder learn from my strategies",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => {
      expect(mockedContinue.mock.calls[0]?.[0]).toBe(false);
    });
  });

  it("stays open when Escape is pressed", async () => {
    mockedGet.mockResolvedValue(DUE);

    render(<DataNotice />);
    const notice = await screen.findByRole("alertdialog");
    fireEvent.keyDown(notice, { key: "Escape" });

    expect(screen.getByRole("alertdialog")).toBeVisible();
  });

  it("stays open and says so when the choice is not saved", async () => {
    mockedGet.mockResolvedValue(DUE);
    mockedContinue.mockRejectedValue(new Error("POST failed: 500"));

    render(<DataNotice />);
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your choice was not saved. Try again.",
    );
    expect(screen.getByRole("alertdialog")).toBeVisible();
  });

  it("shows nothing to an account that has seen this version", async () => {
    mockedGet.mockResolvedValue(seen(true));

    render(<DataNotice />);

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalled();
    });
    expect(screen.queryByRole("alertdialog")).toBe(null);
  });
});

describe("DataNotice before the session is ready", () => {
  it("asks nothing while the token refresh has not settled", async () => {
    authState.refreshed = false;
    mockedGet.mockResolvedValue(DUE);

    render(<DataNotice />);

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBe(null);
    });
    expect(mockedGet).not.toHaveBeenCalled();
  });

  it("asks nothing of a visitor who is not signed in", async () => {
    authState.signedIn = false;
    mockedGet.mockResolvedValue(DUE);

    render(<DataNotice />);

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBe(null);
    });
    expect(mockedGet).not.toHaveBeenCalled();
  });
});
