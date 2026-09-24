// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

vi.mock("@/features/settings/api/memories", () => ({
  searchMemories: vi.fn(),
}));

import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { searchMemories } from "@/features/settings/api/memories";
import type { MemoryItem } from "@pathfinder/shared";
import { MemorySearch } from "./MemorySearch";

const mockedSearch = vi.mocked(searchMemories);

beforeEach(() => {
  mockedSearch.mockReset();
});

afterEach(() => {
  cleanup();
});

function hit(name: string): MemoryItem {
  return {
    key: `k-${name}`,
    value: {
      kind: "knowledge",
      name,
      summary: `${name} summary`,
      tags: [],
      content: {},
      autoRetrieve: true,
      createdAt: new Date().toISOString(),
    },
  };
}

describe("MemorySearch", () => {
  it("renders an empty prompt and does not call the api without a query", () => {
    render(<MemorySearch />);
    expect(screen.getByPlaceholderText(/search memories/i)).toBeInTheDocument();
    expect(mockedSearch).not.toHaveBeenCalled();
  });

  it("debounces search and renders hits", async () => {
    mockedSearch.mockResolvedValue({ hits: [hit("alpha")] });
    render(<MemorySearch />);
    const input = screen.getByPlaceholderText(/search memories/i);
    fireEvent.change(input, { target: { value: "alp" } });
    // Immediate: no call yet.
    expect(mockedSearch).not.toHaveBeenCalled();
    await waitFor(
      () => {
        expect(mockedSearch).toHaveBeenCalledWith("alp");
      },
      { timeout: 2000 },
    );
    expect(await screen.findByText("alpha")).toBeInTheDocument();
  });

  it("shows no-results message when hits are empty", async () => {
    mockedSearch.mockResolvedValue({ hits: [] });
    render(<MemorySearch />);
    fireEvent.change(screen.getByPlaceholderText(/search memories/i), {
      target: { value: "nomatch" },
    });
    await waitFor(
      () => {
        expect(mockedSearch).toHaveBeenCalledWith("nomatch");
      },
      { timeout: 2000 },
    );
    expect(await screen.findByText(/no memories/i)).toBeInTheDocument();
  });

  it("reports a failed search once, with no toast", async () => {
    mockedSearch.mockRejectedValue(new Error("memory search failed"));
    render(<MemorySearch />, { wrapper: appQueryClientWrapper() });
    fireEvent.change(screen.getByPlaceholderText(/search memories/i), {
      target: { value: "kinase" },
    });
    expect(
      await screen.findByText(
        "Search failed: memory search failed",
        {},
        { timeout: 2000 },
      ),
    ).toBeVisible();
    expect(toastError).not.toHaveBeenCalled();
  });
});
