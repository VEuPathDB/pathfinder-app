// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/features/settings/api/memories", () => ({
  listMemories: vi.fn(),
}));

import { listMemories } from "@/features/settings/api/memories";
import type { MemoryItem, MemoryListResponse } from "@pathfinder/shared";
import { MemoriesPanel } from "./MemoriesPanel";

const mockedList = vi.mocked(listMemories);

function item(name: string, kind: MemoryItem["value"]["kind"]): MemoryItem {
  return {
    key: `k-${name}`,
    value: {
      kind,
      name,
      summary: `${name} summary`,
      tags: [],
      content: {},
      autoRetrieve: true,
      createdAt: new Date().toISOString(),
    },
  };
}

function response(over: Partial<MemoryListResponse>): MemoryListResponse {
  return {
    geneSetNotes: [],
    strategies: [],
    preferences: [],
    knowledge: [],
    cases: [],
    pageSize: 25,
    offset: 0,
    hasMore: false,
    ...over,
  };
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoriesPanel />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedList.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("MemoriesPanel", () => {
  it("shows a case beside the other kinds", async () => {
    mockedList.mockResolvedValue(response({ cases: [item("kinase_hunt", "case")] }));
    renderPanel();
    expect(await screen.findByText("kinase_hunt")).toBeInTheDocument();
    const heading = screen.getAllByText(
      (_content, element) =>
        element?.tagName === "P" && element.textContent === "Cases \u00b7 1",
    );
    expect(heading).toHaveLength(1);
  });

  it("shows the empty state when nothing is stored", async () => {
    mockedList.mockResolvedValue(response({}));
    renderPanel();
    expect(await screen.findByText(/No memories yet/i)).toBeInTheDocument();
  });
});
