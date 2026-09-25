// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { listMemories, searchMemories, editMemory, deleteMemory } from "./memories";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

const EMPTY_LIST = {
  geneSetNotes: [],
  strategies: [],
  preferences: [],
  knowledge: [],
  cases: [],
  pageSize: 50,
  offset: 0,
  hasMore: false,
};

function memory(name: string) {
  return {
    key: "k1",
    value: {
      kind: "knowledge",
      name,
      summary: "u",
      tags: [],
      content: {},
      autoRetrieve: true,
      createdAt: "2026-09-24T10:00:00Z",
    },
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function notFound(): Response {
  return new Response(
    JSON.stringify({
      type: "/errors/NOT_FOUND",
      title: "Not found",
      status: 404,
      detail: "Memory k1 not found",
      code: "NOT_FOUND",
    }),
    { status: 404, headers: { "content-type": "application/problem+json" } },
  );
}

function calledUrl(spy: ReturnType<typeof vi.fn>): URL {
  const [url] = spy.mock.calls[0] as [string, RequestInit];
  return new URL(url);
}

describe("memories API client", () => {
  it("lists memories grouped by namespace", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(json(EMPTY_LIST));
    const result = await listMemories();
    expect(result).toEqual(EMPTY_LIST);
  });

  it("sends the page and the credentials on list", async () => {
    const spy = vi.fn().mockResolvedValue(json(EMPTY_LIST));
    globalThis.fetch = spy;
    await listMemories({ limit: 50, offset: 100 });
    const url = calledUrl(spy);
    expect(url.pathname).toBe("/api/v1/memories");
    expect(url.search).toBe("?limit=50&offset=100");
    expect(spy.mock.calls[0]?.[1]).toMatchObject({ credentials: "include" });
  });

  it("searches memories", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(json({ hits: [memory("a")] }));
    const result = await searchMemories("malaria");
    expect(result.hits.map((hit) => hit.value.name)).toEqual(["a"]);
  });

  it("encodes the search query", async () => {
    const spy = vi.fn().mockResolvedValue(json({ hits: [] }));
    globalThis.fetch = spy;
    await searchMemories("mal aria");
    const url = calledUrl(spy);
    expect(url.pathname).toBe("/api/v1/memories/search");
    expect(url.searchParams.get("q")).toBe("mal aria");
  });

  it("deletes memory with the kind query param and an encoded key", async () => {
    const spy = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    globalThis.fetch = spy;
    await deleteMemory("case:plasmodb/1", "knowledge");
    const url = calledUrl(spy);
    expect(url.pathname).toBe("/api/v1/memories/case%3Aplasmodb%2F1");
    expect(url.search).toBe("?kind=knowledge");
    expect(spy.mock.calls[0]?.[1]).toMatchObject({
      method: "DELETE",
      credentials: "include",
    });
  });

  it("edits memory", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(json(memory("new")));
    const result = await editMemory("k1", "knowledge", { name: "new" });
    expect(result.key).toBe("k1");
    expect(result.value.name).toBe("new");
  });

  it("sends PATCH body on edit", async () => {
    const spy = vi.fn().mockResolvedValue(json(memory("a")));
    globalThis.fetch = spy;
    await editMemory("k1", "knowledge", { name: "a", autoRetrieve: true });
    expect(spy).toHaveBeenCalledTimes(1);
    const url = calledUrl(spy);
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(url.pathname).toBe("/api/v1/memories/k1");
    expect(url.search).toBe("?kind=knowledge");
    expect(init.method).toBe("PATCH");
    expect(init.credentials).toBe("include");
    expect(init.body).toBe(JSON.stringify({ name: "a", autoRetrieve: true }));
  });

  it("rejects a refused edit with the problem detail", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(notFound());
    await expect(
      editMemory("k1", "knowledge", { autoRetrieve: false }),
    ).rejects.toThrow("Memory k1 not found");
  });

  it("rejects a refused delete with the problem detail", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(notFound());
    await expect(deleteMemory("k1", "knowledge")).rejects.toThrow(
      "Memory k1 not found",
    );
  });

  it("rejects a failed list with the status when the body says nothing", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(null, { status: 500, statusText: "Internal Server Error" }),
      );
    await expect(listMemories()).rejects.toThrow("HTTP 500 Internal Server Error");
  });
});
