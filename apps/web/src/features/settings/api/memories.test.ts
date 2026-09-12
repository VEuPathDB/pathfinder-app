import { describe, it, expect, vi, afterEach } from "vitest";
import { listMemories, searchMemories, editMemory, deleteMemory } from "./memories";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("memories API client", () => {
  it("lists memories grouped by namespace", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          geneSetNotes: [],
          strategies: [],
          preferences: [],
          knowledge: [],
        }),
        { status: 200 },
      ),
    );
    const result = await listMemories();
    expect(result.geneSetNotes).toEqual([]);
    expect(result.strategies).toEqual([]);
    expect(result.preferences).toEqual([]);
    expect(result.knowledge).toEqual([]);
  });

  it("includes credentials on list", async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          geneSetNotes: [],
          strategies: [],
          preferences: [],
          knowledge: [],
        }),
        { status: 200 },
      ),
    );
    globalThis.fetch = spy;
    await listMemories();
    expect(spy).toHaveBeenCalledWith(
      "/api/v1/memories",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("searches memories", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ hits: [] }), { status: 200 }));
    const result = await searchMemories("malaria");
    expect(result.hits).toEqual([]);
  });

  it("encodes the search query", async () => {
    const spy = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ hits: [] }), { status: 200 }));
    globalThis.fetch = spy;
    await searchMemories("mal aria");
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/memories/search?q=mal%20aria"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("deletes memory with kind query param", async () => {
    const spy = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    globalThis.fetch = spy;
    await deleteMemory("some-key", "knowledge");
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/memories/some-key?kind=knowledge"),
      expect.objectContaining({ method: "DELETE", credentials: "include" }),
    );
  });

  it("edits memory", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          key: "k1",
          value: {
            kind: "knowledge",
            name: "new",
            summary: "u",
            tags: [],
            content: {},
            autoRetrieve: true,
            createdAt: new Date().toISOString(),
          },
        }),
        { status: 200 },
      ),
    );
    const result = await editMemory("k1", "knowledge", { name: "new" });
    expect(result.key).toBe("k1");
  });

  it("sends PATCH body on edit", async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          key: "k1",
          value: {
            kind: "knowledge",
            name: "a",
            summary: "b",
            tags: [],
            content: {},
            autoRetrieve: true,
            createdAt: new Date().toISOString(),
          },
        }),
        { status: 200 },
      ),
    );
    globalThis.fetch = spy;
    await editMemory("k1", "knowledge", { name: "a", autoRetrieve: true });
    // Header shape (X-Requested-With + Content-Type) is enforced by the
    // backend CSRF contract test; this test pins the method + body only.
    expect(spy).toHaveBeenCalledTimes(1);
    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/memories/k1?kind=knowledge");
    expect(init.method).toBe("PATCH");
    expect(init.credentials).toBe("include");
    expect(init.body).toBe(JSON.stringify({ name: "a", autoRetrieve: true }));
  });

  it("throws on non-ok list response", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));
    await expect(listMemories()).rejects.toThrow(/listMemories/);
  });
});
