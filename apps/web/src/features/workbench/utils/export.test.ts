import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import type { GeneSet } from "@pathfinder/shared";
import { exportAsTxt, exportAsCsv, exportMultipleAsCsv } from "./export";

// ---------------------------------------------------------------------------
// Mock DOM APIs used by downloadBlob
// ---------------------------------------------------------------------------

let appendedElements: HTMLElement[] = [];
let removedElements: HTMLElement[] = [];
let createdObjectURLs: string[] = [];
let revokedObjectURLs: string[] = [];
let lastAnchorProps: { href: string; download: string } | null = null;
let downloadedContents: string[] = [];
let clickSpy: ReturnType<typeof vi.fn>;

interface MockBlobShape {
  content: string[];
  type: string;
}

beforeEach(() => {
  appendedElements = [];
  removedElements = [];
  createdObjectURLs = [];
  revokedObjectURLs = [];
  lastAnchorProps = null;
  downloadedContents = [];
  clickSpy = vi.fn();

  vi.stubGlobal("URL", {
    createObjectURL: vi.fn((blob: Blob) => {
      downloadedContents.push((blob as unknown as MockBlobShape).content.join(""));
      const url = `blob:mock-${createdObjectURLs.length}`;
      createdObjectURLs.push(url);
      return url;
    }),
    revokeObjectURL: vi.fn((url: string) => {
      revokedObjectURLs.push(url);
    }),
  });

  vi.stubGlobal(
    "Blob",
    class MockBlob {
      content: string[];
      type: string;
      constructor(parts: string[], opts: { type: string }) {
        this.content = parts;
        this.type = opts.type;
      }
    },
  );

  const mockBody = {
    appendChild: vi.fn((el: HTMLElement) => appendedElements.push(el)),
    removeChild: vi.fn((el: HTMLElement) => removedElements.push(el)),
  };

  vi.stubGlobal("document", {
    createElement: vi.fn((tag: string) => {
      const el = {
        tagName: tag.toUpperCase(),
        href: "",
        download: "",
        click: clickSpy,
      };
      // Track property assignment
      const proxy = new Proxy(el, {
        set(target, prop, value) {
          if (prop === "href" || prop === "download") {
            lastAnchorProps ??= { href: "", download: "" };
            lastAnchorProps[prop] = value as string;
          }
          (target as Record<string | symbol, unknown>)[prop] = value;
          return true;
        },
      });
      return proxy;
    }),
    body: mockBody,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeGeneSet(overrides: Partial<GeneSet> = {}): GeneSet {
  return {
    id: "gs-1",
    name: "Test Set",
    siteId: "plasmodb",
    geneIds: ["PF3D7_0100100", "PF3D7_0200200"],
    geneCount: 2,
    source: "paste",
    stepCount: 1,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// exportAsTxt
// ---------------------------------------------------------------------------

describe("exportAsTxt", () => {
  it("triggers download with one gene ID per line", () => {
    const gs = makeGeneSet();

    exportAsTxt(gs);

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(createdObjectURLs).toHaveLength(1);
    expect(revokedObjectURLs).toHaveLength(1);
    expect(lastAnchorProps?.download).toBe("Test_Set_gene_ids.txt");
  });

  it("does nothing when geneIds is empty", () => {
    const gs = makeGeneSet({ geneIds: [] });

    exportAsTxt(gs);

    expect(clickSpy).not.toHaveBeenCalled();
    expect(createdObjectURLs).toHaveLength(0);
  });

  it("sanitizes filename by replacing special characters", () => {
    const gs = makeGeneSet({ name: "My Set (v2) #test!" });

    exportAsTxt(gs);

    expect(lastAnchorProps?.download).toBe("My_Set__v2___test__gene_ids.txt");
  });

  it("handles gene set with a single gene ID", () => {
    const gs = makeGeneSet({ geneIds: ["ONLY_GENE"] });

    exportAsTxt(gs);

    expect(downloadedContents).toEqual(["ONLY_GENE"]);
  });

  it("appends and removes the anchor element from document.body", () => {
    const gs = makeGeneSet();

    exportAsTxt(gs);

    expect(appendedElements).toHaveLength(1);
    expect(removedElements).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// exportAsCsv
// ---------------------------------------------------------------------------

describe("exportAsCsv", () => {
  it("triggers download with gene_id header and gene IDs", () => {
    const gs = makeGeneSet();

    exportAsCsv(gs);

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(lastAnchorProps?.download).toBe("Test_Set_gene_ids.csv");
  });

  it("does nothing when geneIds is empty", () => {
    const gs = makeGeneSet({ geneIds: [] });

    exportAsCsv(gs);

    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("sanitizes filename", () => {
    const gs = makeGeneSet({ name: "results@2024" });

    exportAsCsv(gs);

    expect(lastAnchorProps?.download).toBe("results_2024_gene_ids.csv");
  });
});

// ---------------------------------------------------------------------------
// exportMultipleAsCsv
// ---------------------------------------------------------------------------

describe("exportMultipleAsCsv", () => {
  it("exports multiple gene sets with set membership columns", () => {
    const sets = [
      makeGeneSet({ id: "gs-1", name: "SetA", source: "paste" }),
      makeGeneSet({
        id: "gs-2",
        name: "SetB",
        source: "strategy",
        geneIds: ["G1"],
      }),
    ];

    exportMultipleAsCsv(sets);

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(lastAnchorProps?.download).toBe("gene_sets_export.csv");
  });

  it("uses single-set filename when only one set has gene IDs", () => {
    const sets = [
      makeGeneSet({ id: "gs-1", name: "OnlySet", geneIds: ["G1"] }),
      makeGeneSet({ id: "gs-2", name: "EmptySet", geneIds: [] }),
    ];

    exportMultipleAsCsv(sets);

    expect(lastAnchorProps?.download).toBe("OnlySet_gene_ids.csv");
  });

  it("does nothing when all sets are empty", () => {
    const sets = [
      makeGeneSet({ geneIds: [] }),
      makeGeneSet({ id: "gs-2", geneIds: [] }),
    ];

    exportMultipleAsCsv(sets);

    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("does nothing when given an empty array", () => {
    exportMultipleAsCsv([]);

    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("filters out sets with no gene IDs", () => {
    const sets = [
      makeGeneSet({ id: "gs-1", name: "Has Genes", geneIds: ["G1", "G2"] }),
      makeGeneSet({ id: "gs-2", name: "No Genes", geneIds: [] }),
    ];

    exportMultipleAsCsv(sets);

    // Should only export the set with gene IDs; file named after single remaining set
    expect(lastAnchorProps?.download).toBe("Has_Genes_gene_ids.csv");
  });

  it("escapes commas in gene set names", () => {
    const sets = [makeGeneSet({ name: "Set A, variant 1", geneIds: ["G1"] })];

    exportMultipleAsCsv(sets);

    expect(downloadedContents).toEqual([
      'gene_id,gene_set_name,source\nG1,"Set A, variant 1",paste',
    ]);
  });

  it("revokes object URL after download", () => {
    const sets = [makeGeneSet({ geneIds: ["G1"] })];

    exportMultipleAsCsv(sets);

    expect(revokedObjectURLs).toHaveLength(1);
    expect(revokedObjectURLs[0]).toBe(createdObjectURLs[0]);
  });
});
