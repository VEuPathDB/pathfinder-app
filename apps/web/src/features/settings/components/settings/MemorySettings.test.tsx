// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));

vi.mock("@/features/settings/api/memories", () => ({
  listMemories: vi.fn(),
  searchMemories: vi.fn(),
  editMemory: vi.fn(),
  deleteMemory: vi.fn(),
}));

import { appQueryClientWrapper } from "@/app/components/__fixtures__/appQueryClient";
import { APIError } from "@/lib/api/http";
import {
  deleteMemory,
  editMemory,
  listMemories,
} from "@/features/settings/api/memories";
import type { MemoryItem, MemoryListResponse } from "@pathfinder/shared";
import { useMemoryFocusStore } from "@/state/useMemoryFocusStore";
import { MemorySettings } from "./MemorySettings";

const mockedList = vi.mocked(listMemories);
const mockedEdit = vi.mocked(editMemory);
const mockedDelete = vi.mocked(deleteMemory);

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

function notFound(key: string): APIError {
  const detail = `Memory ${key} not found`;
  return new APIError(detail, {
    status: 404,
    statusText: "Not Found",
    url: `http://localhost:3000/api/v1/memories/${key}`,
    data: {
      type: "/errors/NOT_FOUND",
      title: "Not found",
      status: 404,
      detail,
      code: "NOT_FOUND",
    },
  });
}

function emptyList(): MemoryListResponse {
  return {
    geneSetNotes: [],
    strategies: [],
    preferences: [],
    knowledge: [],
    cases: [],
    pageSize: 50,
    offset: 0,
    hasMore: false,
  };
}

beforeEach(() => {
  mockedList.mockReset();
  mockedEdit.mockReset();
  mockedDelete.mockReset();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useMemoryFocusStore.getState().clearFocus();
});

/** Render with the first page already cached, so the accordions paint at once. */
function renderWith(list: MemoryListResponse): void {
  mockedList.mockResolvedValue(list);
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  qc.setQueryData(["memories", "list", 0], list);
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  render(<MemorySettings />, { wrapper: Wrapper });
}

describe("MemorySettings", () => {
  it("renders five MemorySection accordions", () => {
    renderWith(emptyList());
    expect(screen.getByRole("button", { name: /Gene sets/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Strategies/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Preferences/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Knowledge/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cases/i })).toBeInTheDocument();
  });

  it("deletes a case like any other kind", async () => {
    mockedDelete.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderWith({ ...emptyList(), cases: [item("kinase_hunt", "case")] });
    fireEvent.click(screen.getByRole("button", { name: /Cases/i }));
    fireEvent.click(screen.getByLabelText(/delete kinase_hunt/i));
    await waitFor(() => {
      expect(mockedDelete).toHaveBeenCalledWith("k-kinase_hunt", "case");
    });
  });

  it("shows error state on failed list", async () => {
    mockedList.mockRejectedValue(new Error("boom"));
    render(<MemorySettings />);
    await waitFor(() => {
      expect(screen.getByText(/Failed to load/i)).toBeInTheDocument();
    });
  });

  it("reports a failed list once, with no toast", async () => {
    mockedList.mockRejectedValue(new Error("memory list failed"));
    render(<MemorySettings />, { wrapper: appQueryClientWrapper() });
    expect(
      await screen.findByText("Failed to load memories: memory list failed"),
    ).toBeVisible();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("deletes memory on confirmed delete", async () => {
    mockedDelete.mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderWith({
      ...emptyList(),
      geneSetNotes: [item("drug_targets", "gene_set_note")],
    });
    fireEvent.click(screen.getByRole("button", { name: /Gene sets/i }));
    fireEvent.click(screen.getByLabelText(/delete drug_targets/i));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      expect(mockedDelete).toHaveBeenCalledWith("k-drug_targets", "gene_set_note");
    });
  });

  it("skips delete when user cancels confirm", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderWith({
      ...emptyList(),
      geneSetNotes: [item("drug_targets", "gene_set_note")],
    });
    fireEvent.click(screen.getByRole("button", { name: /Gene sets/i }));
    fireEvent.click(screen.getByLabelText(/delete drug_targets/i));
    expect(mockedDelete).not.toHaveBeenCalled();
  });

  it("calls editMemory on auto-retrieve toggle", async () => {
    const k = item("my_knowledge", "knowledge");
    mockedEdit.mockResolvedValue(k);
    renderWith({ ...emptyList(), knowledge: [k] });
    fireEvent.click(screen.getByRole("button", { name: /Knowledge/i }));
    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => {
      expect(mockedEdit).toHaveBeenCalledWith("k-my_knowledge", "knowledge", {
        autoRetrieve: false,
      });
    });
  });

  it("opens editor on row click and saves edits", async () => {
    const k = item("my_knowledge", "knowledge");
    mockedEdit.mockResolvedValue(k);
    renderWith({ ...emptyList(), knowledge: [k] });
    fireEvent.click(screen.getByRole("button", { name: /Knowledge/i }));
    fireEvent.click(screen.getByTestId("memory-row-body"));
    expect(screen.getByRole("dialog", { name: /edit memory/i })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^name$/i), {
      target: { value: "Updated" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(mockedEdit).toHaveBeenCalled();
    });
    const [, kind, body] = mockedEdit.mock.calls[0] ?? [];
    expect(kind).toBe("knowledge");
    expect(body?.name).toBe("Updated");
  });

  it("requests next page when Load more clicked", async () => {
    renderWith({
      ...emptyList(),
      geneSetNotes: [item("first_page", "gene_set_note")],
      hasMore: true,
    });
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => {
      expect(mockedList).toHaveBeenCalled();
    });
    expect(mockedList.mock.calls.at(-1)?.[0]).toMatchObject({
      limit: 50,
      offset: 50,
    });
  });

  it("says why a failed edit did not save", async () => {
    const k = item("my_knowledge", "knowledge");
    mockedEdit.mockRejectedValue(notFound("k-my_knowledge"));
    renderWith({ ...emptyList(), knowledge: [k] });
    fireEvent.click(screen.getByRole("button", { name: /Knowledge/i }));
    fireEvent.click(screen.getByTestId("memory-row-body"));
    fireEvent.change(screen.getByLabelText(/^name$/i), {
      target: { value: "Updated" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      'Could not save "my_knowledge": Memory k-my_knowledge not found',
    );
    expect(screen.getByLabelText(/^name$/i)).toHaveValue("Updated");
  });

  it("says why a failed delete kept the memory", async () => {
    mockedDelete.mockRejectedValue(notFound("k-drug_targets"));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderWith({
      ...emptyList(),
      geneSetNotes: [item("drug_targets", "gene_set_note")],
    });
    fireEvent.click(screen.getByRole("button", { name: /Gene sets/i }));
    fireEvent.click(screen.getByLabelText(/delete drug_targets/i));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      'Could not delete "drug_targets": Memory k-drug_targets not found',
    );
  });

  it("says why a failed auto-retrieve toggle did not change", async () => {
    mockedEdit.mockRejectedValue(notFound("k-my_knowledge"));
    renderWith({ ...emptyList(), knowledge: [item("my_knowledge", "knowledge")] });
    fireEvent.click(screen.getByRole("button", { name: /Knowledge/i }));
    fireEvent.click(screen.getByRole("checkbox"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      'Could not change auto-retrieve for "my_knowledge": Memory k-my_knowledge not found',
    );
  });

  it("hides Load more when hasMore is false", () => {
    renderWith(emptyList());
    expect(
      screen.queryByRole("button", { name: /load more/i }),
    ).not.toBeInTheDocument();
  });

  it("opens the section of a focused memory and marks its row", () => {
    useMemoryFocusStore.getState().focusMemory("k-kinase_hunt", "case");
    renderWith({
      ...emptyList(),
      cases: [item("kinase_hunt", "case"), item("vaccine_antigens", "case")],
      knowledge: [item("my_knowledge", "knowledge")],
    });
    expect(screen.getByRole("button", { name: /Cases/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("button", { name: /Knowledge/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    const rows = screen.getAllByTestId("memory-row-body");
    expect(rows.map((row) => row.getAttribute("aria-current"))).toEqual(["true", null]);
  });
});
