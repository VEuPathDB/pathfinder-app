// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@pathfinder/shared/generated/hooks/useListScratchpadNotes", () => ({
  listScratchpadNotes: vi.fn(),
  listScratchpadNotesQueryOptions: (conversationId: string) => ({
    queryKey: [
      {
        url: "/api/v1/conversations/:conversation_id/scratchpad/notes",
        params: { conversation_id: conversationId },
      },
    ] as const,
    queryFn: () => mockedList(conversationId),
  }),
}));

vi.mock("@pathfinder/shared/generated/hooks/usePatchScratchpadNote", () => ({
  patchScratchpadNote: vi.fn(),
}));

vi.mock("@pathfinder/shared/generated/hooks/useDeleteScratchpadNote", () => ({
  deleteScratchpadNote: vi.fn(),
}));

import {
  listScratchpadNotes,
  listScratchpadNotesQueryOptions,
} from "@pathfinder/shared/generated/hooks/useListScratchpadNotes";
import { patchScratchpadNote } from "@pathfinder/shared/generated/hooks/usePatchScratchpadNote";
import { deleteScratchpadNote } from "@pathfinder/shared/generated/hooks/useDeleteScratchpadNote";
import type { Note } from "@pathfinder/shared/generated/types/Note";

import { ScratchpadPanel } from "./ScratchpadPanel";

const mockedList = vi.mocked(listScratchpadNotes);
const mockedPatch = vi.mocked(patchScratchpadNote);
const mockedDelete = vi.mocked(deleteScratchpadNote);

function wrap(ui: React.ReactNode, seed?: Note[]) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  if (seed !== undefined) {
    qc.setQueryData(listScratchpadNotesQueryOptions("c1").queryKey, seed);
  }
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

function buildNote(overrides: Partial<Note> & Pick<Note, "id" | "title">): Note {
  const now = new Date().toISOString();
  return {
    conversationId: "c1",
    summary: "s",
    body: "b",
    tags: [],
    pinned: false,
    bodyTokens: 1,
    createdAt: now,
    updatedAt: now,
    ...overrides,
  };
}

describe("ScratchpadPanel", () => {
  beforeEach(() => {
    mockedList.mockReset();
    mockedPatch.mockReset();
    mockedDelete.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders empty state when no notes", async () => {
    mockedList.mockResolvedValue([]);
    render(wrap(<ScratchpadPanel conversationId="c1" />));
    await waitFor(() => {
      expect(screen.getByText(/no notes/i)).toBeInTheDocument();
    });
  });

  it("renders pinned group above unpinned", async () => {
    mockedList.mockResolvedValue([
      buildNote({ id: "n-aaa111", title: "UNPINNED_ONE", pinned: false }),
      buildNote({ id: "n-bbb222", title: "PINNED_ONE", pinned: true }),
    ]);

    render(wrap(<ScratchpadPanel conversationId="c1" />));
    await waitFor(() => {
      expect(screen.getByText("PINNED_ONE")).toBeInTheDocument();
      expect(screen.getByText("UNPINNED_ONE")).toBeInTheDocument();
    });

    const pinned = screen.getByText("PINNED_ONE");
    const unpinned = screen.getByText("UNPINNED_ONE");
    // Pinned section appears before unpinned section in the DOM.
    expect(
      pinned.compareDocumentPosition(unpinned) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("pin toggle calls PATCH", async () => {
    const note = buildNote({ id: "n-xyz", title: "T", pinned: false });
    mockedList.mockResolvedValue([note]);
    mockedPatch.mockResolvedValue(buildNote({ id: "n-xyz", title: "T", pinned: true }));

    render(wrap(<ScratchpadPanel conversationId="c1" />, [note]));
    await userEvent.click(screen.getByRole("button", { name: /^pin$/i }));
    // (conversation_id, note_id, data) - matches the generated client signature.
    expect(mockedPatch).toHaveBeenCalledWith("c1", "n-xyz", { pinned: true });
  });
});
