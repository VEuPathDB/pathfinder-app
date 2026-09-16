import { describe, expect, it } from "vitest";
import { extractVocabOptions, extractVocabTree } from "./vocab";

// ── extractVocabOptions ────────────────────────────────────────

describe("extractVocabOptions", () => {
  // -- Array inputs --

  it("extracts from a flat array of strings", () => {
    const result = extractVocabOptions(["alpha", "beta", "gamma"]);
    expect(result).toHaveLength(3);
    expect(result[0]!).toMatchObject({ value: "alpha", label: "alpha" });
    expect(result[2]!).toMatchObject({ value: "gamma", label: "gamma" });
  });

  it("extracts from a flat array of numbers", () => {
    const result = extractVocabOptions([1, 2, 3]);
    expect(result).toHaveLength(3);
    expect(result[0]!.value).toBe("1");
  });

  it("extracts from an array of [value, label] tuples", () => {
    const result = extractVocabOptions([
      ["v1", "Label 1"],
      ["v2", "Label 2"],
    ]);
    expect(result).toHaveLength(2);
    expect(result[0]!).toMatchObject({ value: "v1", label: "Label 1" });
  });

  it("extracts from an array of objects with value/label fields", () => {
    const result = extractVocabOptions([
      { value: "a", label: "Alpha" },
      { value: "b", display: "Beta Display" },
    ]);
    expect(result).toHaveLength(2);
    expect(result[0]!).toMatchObject({ value: "a", label: "Alpha" });
    expect(result[1]!).toMatchObject({ value: "b", label: "Beta Display" });
  });

  it("extracts from objects using id, term, name, displayName", () => {
    expect(extractVocabOptions([{ id: "x" }])[0]!.value).toBe("x");
    expect(extractVocabOptions([{ term: "y" }])[0]!.value).toBe("y");
    expect(extractVocabOptions([{ name: "z" }])[0]!.value).toBe("z");
    expect(extractVocabOptions([{ displayName: "w" }])[0]!.value).toBe("w");
  });

  // -- Wrapped object inputs --

  it("extracts from { values: [...] }", () => {
    const result = extractVocabOptions({ values: ["one", "two"] });
    expect(result).toHaveLength(2);
    expect(result.map((o) => o.value)).toEqual(["one", "two"]);
  });

  it("extracts from { items: [...] }", () => {
    const result = extractVocabOptions({ items: ["a"] });
    expect(result).toHaveLength(1);
  });

  it("extracts from { terms: [...] }", () => {
    const result = extractVocabOptions({ terms: ["t1", "t2"] });
    expect(result).toHaveLength(2);
  });

  it("extracts from { options: [...] }", () => {
    const result = extractVocabOptions({ options: ["opt1"] });
    expect(result).toHaveLength(1);
  });

  it("extracts from { allowedValues: [...] }", () => {
    const result = extractVocabOptions({ allowedValues: ["av1", "av2"] });
    expect(result).toHaveLength(2);
  });

  it("extracts from a values object (key-value map)", () => {
    const result = extractVocabOptions({
      values: { key1: "Label 1", key2: "Label 2" },
    });
    expect(result).toHaveLength(2);
    expect(result[0]!).toMatchObject({ value: "key1", label: "Label 1" });
  });

  it("handles values object with non-string/number val (label becomes undefined)", () => {
    const result = extractVocabOptions({
      values: { key1: { nested: true } },
    });
    expect(result).toHaveLength(1);
    expect(result[0]!.value).toBe("key1");
  });

  // -- Tree inputs --

  it("walks a tree structure with data nodes", () => {
    const tree = {
      data: { value: "root", display: "Root Node" },
      children: [
        { data: { value: "child1", display: "Child 1" } },
        { data: { value: "child2", display: "Child 2" } },
      ],
    };
    const result = extractVocabOptions(tree);
    expect(result).toHaveLength(3);
    expect(result[0]!).toMatchObject({
      value: "root",
      label: "Root Node",
      depth: 0,
    });
    expect(result[1]!).toMatchObject({
      value: "child1",
      label: "Child 1",
      depth: 1,
    });
  });

  it("generates displayLabel with indentation for nested nodes", () => {
    const tree = {
      data: { value: "a" },
      children: [
        {
          data: { value: "b" },
          children: [{ data: { value: "c" } }],
        },
      ],
    };
    const result = extractVocabOptions(tree);
    expect(result[0]!.displayLabel).toBe("a");
    expect(result[1]!.displayLabel).toBe("- b"); // "- b"
    expect(result[2]!.displayLabel).toBe("- - c"); // "- - c"
  });

  // -- Deduplication --

  it("deduplicates entries by trimmed value", () => {
    const result = extractVocabOptions(["dup", "dup", "unique"]);
    expect(result).toHaveLength(2);
  });

  // -- Limit --

  it("respects the limit parameter", () => {
    const big = Array.from({ length: 500 }, (_, i) => `item${i}`);
    const result = extractVocabOptions(big, 10);
    expect(result).toHaveLength(10);
  });

  it("uses default limit of 200", () => {
    const big = Array.from({ length: 300 }, (_, i) => `item${i}`);
    const result = extractVocabOptions(big);
    expect(result).toHaveLength(200);
  });

  // -- @@fake@@ sentinel --

  it('maps @@fake@@ value to "All" label', () => {
    const result = extractVocabOptions(["@@fake@@"]);
    expect(result[0]!).toMatchObject({
      value: "@@fake@@",
      label: "All",
      rawLabel: "All",
    });
  });

  // -- Edge cases --

  it("returns empty array for null/undefined input", () => {
    expect(extractVocabOptions(null)).toEqual([]);
    expect(extractVocabOptions(undefined)).toEqual([]);
  });

  it("returns empty array for primitive input", () => {
    expect(extractVocabOptions(42)).toEqual([]);
    expect(extractVocabOptions("string")).toEqual([]);
  });

  it("skips empty/whitespace-only string entries", () => {
    const result = extractVocabOptions(["", "  ", "valid"]);
    expect(result).toHaveLength(1);
    expect(result[0]!.value).toBe("valid");
  });

  it("skips array entries with undefined value", () => {
    const result = extractVocabOptions([[undefined]]);
    expect(result).toHaveLength(0);
  });

  it("handles tuple where label is falsy", () => {
    const result = extractVocabOptions([["val", ""]]);
    expect(result[0]!).toMatchObject({ value: "val" });
  });

  it("handles empty array", () => {
    expect(extractVocabOptions([])).toEqual([]);
  });

  it("handles empty wrapper object", () => {
    expect(extractVocabOptions({})).toEqual([]);
  });
});

// ── extractVocabTree ──────────────────────────────────────────

describe("extractVocabTree", () => {
  it("extracts a tree from an array of objects with children", () => {
    const input = [
      {
        data: { value: "root" },
        children: [{ data: { value: "leaf" } }],
      },
    ];
    const result = extractVocabTree(input);
    expect(result).not.toBeNull();
    expect(result).toHaveLength(1);
    expect(result![0]!.value).toBe("root");
    expect(result![0]!.children).toHaveLength(1);
    expect(result![0]!.children![0]!.value).toBe("leaf");
  });

  it("returns null for flat arrays (no children)", () => {
    const flat = [{ data: { value: "a" } }, { data: { value: "b" } }];
    expect(extractVocabTree(flat)).toEqual(null);
    const nested = [{ data: { value: "a" }, children: [{ data: { value: "b" } }] }];
    expect(extractVocabTree(nested)).toMatchObject([{ value: "a" }]);
  });

  it("extracts from wrapper object with values array", () => {
    const input = {
      values: [
        {
          data: { value: "parent" },
          children: [{ data: { value: "child" } }],
        },
      ],
    };
    const result = extractVocabTree(input);
    expect(result).not.toBeNull();
    expect(result![0]!.value).toBe("parent");
  });

  it("extracts from wrapper object with items array", () => {
    const input = {
      items: [
        {
          data: { value: "p" },
          children: [{ data: { value: "c" } }],
        },
      ],
    };
    expect(extractVocabTree(input)).toMatchObject([
      { value: "p", children: [{ value: "c" }] },
    ]);
  });

  it("extracts from wrapper object with terms array", () => {
    const input = {
      terms: [
        {
          data: { value: "t" },
          children: [{ data: { value: "tc" } }],
        },
      ],
    };
    expect(extractVocabTree(input)).toMatchObject([
      { value: "t", children: [{ value: "tc" }] },
    ]);
  });

  it("extracts from wrapper object with options array", () => {
    const input = {
      options: [
        {
          data: { value: "o" },
          children: [{ data: { value: "oc" } }],
        },
      ],
    };
    expect(extractVocabTree(input)).toMatchObject([
      { value: "o", children: [{ value: "oc" }] },
    ]);
  });

  it("extracts from a root object with children property", () => {
    const input = {
      data: { value: "root" },
      children: [{ data: { value: "child" } }],
    };
    const result = extractVocabTree(input);
    expect(result).toHaveLength(1);
    expect(result![0]!.value).toBe("root");
    expect(result![0]!.children).toHaveLength(1);
  });

  it('maps @@fake@@ to "All" label in tree nodes', () => {
    const input = [
      {
        data: { value: "@@fake@@" },
        children: [{ data: { value: "real" } }],
      },
    ];
    const result = extractVocabTree(input);
    expect(result![0]!.label).toBe("All");
  });

  it("extracts label from display/displayName/label/name fields", () => {
    const input = [
      {
        data: { value: "v1", display: "Display Label" },
        children: [{ data: { value: "v2", displayName: "DN" } }],
      },
    ];
    const result = extractVocabTree(input);
    expect(result![0]!.label).toBe("Display Label");
    expect(result![0]!.children![0]!.label).toBe("DN");
  });

  it("uses entry directly as data when no data property exists", () => {
    const input = [
      {
        value: "direct",
        label: "Direct Label",
        children: [{ value: "child-direct" }],
      },
    ];
    const result = extractVocabTree(input);
    expect(result).not.toBeNull();
    expect(result![0]!.value).toBe("direct");
    expect(result![0]!.label).toBe("Direct Label");
  });

  // -- Edge cases --

  it("returns null for null/undefined input", () => {
    expect(extractVocabTree(null)).toEqual(null);
    expect(extractVocabTree(undefined)).toEqual(null);
  });

  it("returns null for primitives", () => {
    expect(extractVocabTree(42)).toEqual(null);
    expect(extractVocabTree("str")).toEqual(null);
  });

  it("returns null for empty array", () => {
    expect(extractVocabTree([])).toEqual(null);
  });

  it("returns null for array of primitives", () => {
    expect(extractVocabTree(["a", "b"])).toEqual(null);
  });

  it("returns null if wrapper values array has no children", () => {
    expect(extractVocabTree({ values: [{ data: { value: "flat" } }] })).toEqual(null);
  });

  it("skips entries with no extractable value", () => {
    const input = [
      { data: {} },
      {
        data: { value: "ok" },
        children: [{ data: { value: "child" } }],
      },
    ];
    const result = extractVocabTree(input);
    expect(result).not.toBeNull();
    // The null entry is filtered out
    expect(result!.every((n) => n.value)).toBe(true);
  });

  it("returns null for object without values/items/terms/options/children", () => {
    expect(extractVocabTree({ random: "stuff" })).toEqual(null);
  });
});
