// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { useForm, useStore } from "@tanstack/react-form";
import {
  buildPhyleticTree,
  encodeProfilePattern,
  decodeProfilePattern,
  leafStates,
  buildSpeciesLists,
  claimsPhyleticParams,
  resolveTerms,
  seedTriStates,
  triStateColor,
} from "./phyleticProfileLogic";
import { PhyleticProfileParam } from "./PhyleticProfileParam";
import type { WDKVocabTerm } from "@strategist/shared";

import type { ParamSpec } from "@/features/strategy/parameters/spec";
import type { ParamForm } from "../hooks/useParamForm";

afterEach(cleanup);

const TERM_MAP_VOCAB: WDKVocabTerm[] = [
  ["ALL", "Root", null],
  ["EUKARYA", "Eukaryota", null],
  ["pfal", "P. falciparum", null],
  ["hsap", "H. sapiens", null],
  ["BACTERIA", "Bacteria", null],
  ["ecol", "E. coli", null],
];

const INDENT_MAP_VOCAB: WDKVocabTerm[] = [
  ["ALL", "0", null],
  ["EUKARYA", "1", null],
  ["pfal", "2", null],
  ["hsap", "2", null],
  ["BACTERIA", "1", null],
  ["ecol", "2", null],
];

const PARAM_DEFAULTS = {
  allowEmptyValue: false,
  countOnlyLeaves: false,
  isNumber: false,
  isVisible: true,
} as const;

const PHYLETIC_DEFAULTS: Record<string, string | string[] | unknown> = {
  profile_pattern: "",
  included_species: "",
  excluded_species: "",
  phyletic_indent_map: INDENT_MAP_VOCAB,
  phyletic_term_map: TERM_MAP_VOCAB,
};

function makeSpecsFor(termMap: WDKVocabTerm[], indentMap: WDKVocabTerm[]): ParamSpec[] {
  return [
    { ...PARAM_DEFAULTS, name: "profile_pattern", type: "string" },
    { ...PARAM_DEFAULTS, name: "included_species", type: "string" },
    { ...PARAM_DEFAULTS, name: "excluded_species", type: "string" },
    {
      ...PARAM_DEFAULTS,
      name: "phyletic_indent_map",
      type: "string",
      vocabulary: indentMap,
    },
    {
      ...PARAM_DEFAULTS,
      name: "phyletic_term_map",
      type: "string",
      vocabulary: termMap,
    },
  ];
}

function makeAllSpecs(): ParamSpec[] {
  return makeSpecsFor(TERM_MAP_VOCAB, INDENT_MAP_VOCAB);
}

// A clade above two leaves, so a stored clade term and its decoded leaves differ.
const CLADE_TERM_MAP: WDKVocabTerm[] = [
  ["ALL", "All Organisms", null],
  ["MAMM", "Mammalia", null],
  ["hsap", "H. sapiens", null],
  ["mmus", "M. musculus", null],
  ["pfal", "P. falciparum", null],
];

const CLADE_INDENT_MAP: WDKVocabTerm[] = [
  ["MAMM", "1", null],
  ["hsap", "2", null],
  ["mmus", "2", null],
  ["pfal", "1", null],
];

function TestForm({
  defaultValues,
  children,
}: {
  defaultValues?: Record<string, unknown>;
  children: (form: ParamForm) => React.ReactNode;
}) {
  const form = useForm({
    defaultValues: { ...PHYLETIC_DEFAULTS, ...defaultValues } as Record<
      string,
      string | string[]
    >,
    onSubmit: () => {},
  });
  return <>{children(form)}</>;
}

function FormValueReader({ form, name }: { form: ParamForm; name: string }) {
  const value = useStore(form.store, (s) => s.values[name]);
  return <output data-testid={`form-${name}`}>{String(value ?? "")}</output>;
}

describe("triStateColor", () => {
  it("names the status tokens, not palette shades", () => {
    expect(triStateColor("include")).toBe("text-success");
    expect(triStateColor("exclude")).toBe("text-destructive");
    expect(triStateColor("unconstrained")).toBe("text-muted-foreground");
  });
});

describe("buildPhyleticTree", () => {
  it("builds correct hierarchy from term/indent map vocabs", () => {
    const roots = buildPhyleticTree(TERM_MAP_VOCAB, INDENT_MAP_VOCAB);
    expect(roots).toHaveLength(2);
    expect(roots[0]!.code).toBe("EUKARYA");
    expect(roots[0]!.children).toHaveLength(2);
    expect(roots[0]!.children[0]!.code).toBe("pfal");
    expect(roots[1]!.code).toBe("BACTERIA");
    expect(roots[1]!.children[0]!.code).toBe("ecol");
  });

  it("returns empty array for null/undefined input", () => {
    expect(buildPhyleticTree(null, null)).toEqual([]);
    expect(buildPhyleticTree(undefined, undefined)).toEqual([]);
  });

  it("handles empty arrays", () => {
    expect(buildPhyleticTree([], [])).toEqual([]);
  });
});

describe("encodeProfilePattern", () => {
  // profile_pattern is a SQL LIKE pattern over a colon-joined species census.
  // The % characters are the wildcard, and the tokens between them are
  // code:Y for present and code:N for absent.
  it("wraps and separates the tokens with the LIKE wildcard", () => {
    const states = new Map([
      ["hsap", "exclude" as const],
      ["pfal", "include" as const],
    ]);

    expect(encodeProfilePattern(states)).toBe("%hsap:N%pfal:Y%");
  });

  it("leaves an unconstrained species out of the pattern", () => {
    const states = new Map([
      ["pfal", "include" as const],
      ["ecol", "unconstrained" as const],
    ]);

    expect(encodeProfilePattern(states)).toBe("%pfal:Y%");
  });

  it("sorts the tokens into ascending code order", () => {
    // The census lists codes ascending, so %B%A% describes a census that
    // cannot exist however correct each token is.
    const clicked = new Map([
      ["yepe", "include" as const],
      ["wsuc", "include" as const],
    ]);

    expect(encodeProfilePattern(clicked)).toBe("%wsuc:Y%yepe:Y%");
  });

  it("writes a bare wildcard for an empty selection", () => {
    // The empty string is the one value WDK refuses: allowEmptyValue is false.
    expect(encodeProfilePattern(new Map())).toBe("%");
  });
});

describe("decodeProfilePattern", () => {
  it("reads back the form the encoder writes", () => {
    const states = decodeProfilePattern("%hsap:N%pfal:Y%");

    expect(states.get("pfal")).toBe("include");
    expect(states.get("hsap")).toBe("exclude");
  });

  it("reads a pattern the backend built", () => {
    const states = decodeProfilePattern("%ggor:N%hsap:N%mmus:N%pfal:Y%");

    expect([...states.keys()].sort()).toEqual(["ggor", "hsap", "mmus", "pfal"]);
    expect(states.get("mmus")).toBe("exclude");
  });

  it("returns nothing for a bare wildcard", () => {
    expect(decodeProfilePattern("%").size).toBe(0);
  });

  it("returns nothing for an empty string", () => {
    expect(decodeProfilePattern("").size).toBe(0);
  });

  it("ignores a token in another site's grammar", () => {
    // hsap=1T is a valid OrthoMCL phyletic_expression, not a profile_pattern.
    expect(decodeProfilePattern("hsap=1T").size).toBe(0);
  });

  it("roundtrips with encodeProfilePattern", () => {
    const original = new Map([
      ["pfal", "include" as const],
      ["hsap", "exclude" as const],
    ]);
    const decoded = decodeProfilePattern(encodeProfilePattern(original));
    expect(decoded.get("pfal")).toBe("include");
    expect(decoded.get("hsap")).toBe("exclude");
  });
});

describe("claimsPhyleticParams", () => {
  it("returns all 5 param names when all present", () => {
    expect(claimsPhyleticParams(makeAllSpecs())).toHaveLength(5);
  });

  it("returns empty array when one param is missing", () => {
    const specs = makeAllSpecs().filter((s) => s.name !== "profile_pattern");
    expect(claimsPhyleticParams(specs)).toEqual([]);
  });

  it("returns empty array for empty specs", () => {
    expect(claimsPhyleticParams([])).toEqual([]);
  });
});

describe("PhyleticProfileParam component", () => {
  const specs = makeAllSpecs();

  it("renders tree nodes from vocab data in form context", () => {
    render(
      <TestForm>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );
    expect(screen.getByText("Eukaryota")).toBeTruthy();
    expect(screen.getByText("Bacteria")).toBeTruthy();
    expect(screen.getByText("P. falciparum")).toBeTruthy();
    expect(screen.getByText("H. sapiens")).toBeTruthy();
    expect(screen.getByText("E. coli")).toBeTruthy();
  });

  it("clicking tri-state icon cycles through states and updates form", () => {
    render(
      <TestForm>
        {(form) => (
          <>
            <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />
            <FormValueReader form={form} name="profile_pattern" />
          </>
        )}
      </TestForm>,
    );

    const pfalRow = screen.getByText("P. falciparum").closest("[data-node]");
    const toggleBtn = pfalRow!.querySelector("[data-toggle]") as HTMLElement;

    fireEvent.click(toggleBtn);
    expect(screen.getByTestId("form-profile_pattern").textContent).toContain(
      "%pfal:Y%",
    );

    fireEvent.click(toggleBtn);
    expect(screen.getByTestId("form-profile_pattern").textContent).toContain(
      "%pfal:N%",
    );

    fireEvent.click(toggleBtn);
    expect(screen.getByTestId("form-profile_pattern").textContent).not.toContain(
      "pfal",
    );
  });

  it("shows correct summary footer counts", () => {
    render(
      <TestForm defaultValues={{ profile_pattern: "%hsap:N%pfal:Y%" }}>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );
    expect(screen.getByText(/1 included/)).toBeTruthy();
    expect(screen.getByText(/1 excluded/)).toBeTruthy();
    expect(screen.getByText(/3 unconstrained/)).toBeTruthy();
  });

  it("search filters tree nodes by label", () => {
    render(
      <TestForm>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "falciparum" },
    });
    expect(screen.getByText("P. falciparum")).toBeTruthy();
    expect(screen.queryByText("E. coli")).toBeNull();
  });

  it("initializes state from existing profile_pattern in form", () => {
    render(
      <TestForm defaultValues={{ profile_pattern: "%pfal:Y%" }}>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );
    const pfalRow = screen.getByText("P. falciparum").closest("[data-node]");
    const toggleBtn = pfalRow!.querySelector("[data-toggle]") as HTMLElement;
    expect(toggleBtn.textContent).toContain("\u2713");
  });

  it("renders legend showing the three states", () => {
    render(
      <TestForm>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );
    expect(screen.getAllByText(/unconstrained/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/include/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/exclude/i).length).toBeGreaterThanOrEqual(2);
  });
});

describe("resolveTerms", () => {
  const roots = buildPhyleticTree(CLADE_TERM_MAP, CLADE_INDENT_MAP);

  it("resolves an exact code", () => {
    expect(resolveTerms(roots, "pfal")).toEqual({ codes: ["pfal"], unknown: [] });
  });

  it("splits a comma separated proposal and trims each term", () => {
    expect(resolveTerms(roots, " MAMM ,  pfal ").codes).toEqual(["MAMM", "pfal"]);
  });

  it("accepts a list as well as a string", () => {
    expect(resolveTerms(roots, ["MAMM", "pfal"]).codes).toEqual(["MAMM", "pfal"]);
  });

  it("drops the empty marker the reference client writes", () => {
    expect(resolveTerms(roots, "n/a")).toEqual({ codes: [], unknown: [] });
  });

  it("matches a display label without regard to case", () => {
    expect(resolveTerms(roots, "mammalia").codes).toEqual(["MAMM"]);
  });

  it("names a term the tree does not carry", () => {
    expect(resolveTerms(roots, "Nosema")).toEqual({ codes: [], unknown: ["Nosema"] });
  });

  it("treats the root as unknown, in both of its spellings", () => {
    expect(resolveTerms(roots, "ALL").unknown).toEqual(["ALL"]);
    expect(resolveTerms(roots, "All Organisms").unknown).toEqual(["All Organisms"]);
  });

  it("keeps one entry per code", () => {
    expect(resolveTerms(roots, "pfal, pfal").codes).toEqual(["pfal"]);
  });

  it("keeps one entry per unknown term", () => {
    expect(resolveTerms(roots, "Nosema, Nosema").unknown).toEqual(["Nosema"]);
  });
});

describe("seedTriStates", () => {
  const roots = buildPhyleticTree(CLADE_TERM_MAP, CLADE_INDENT_MAP);

  it("seeds the clade the lists carry, not the leaves the pattern carries", () => {
    const { states } = seedTriStates(roots, {
      included: "n/a",
      excluded: "MAMM",
      pattern: "%hsap:N%mmus:N%",
    });

    expect([...states.entries()]).toEqual([["MAMM", "exclude"]]);
  });

  it("reads both lists", () => {
    const { states } = seedTriStates(roots, {
      included: "pfal",
      excluded: "MAMM",
      pattern: "%",
    });

    expect(states.get("pfal")).toBe("include");
    expect(states.get("MAMM")).toBe("exclude");
  });

  it("falls back to the pattern when both lists are the empty marker", () => {
    const { states } = seedTriStates(roots, {
      included: "n/a",
      excluded: "n/a",
      pattern: "%hsap:Y%",
    });

    expect(states.get("hsap")).toBe("include");
  });

  it("falls back to the pattern when both lists are absent", () => {
    const { states } = seedTriStates(roots, {
      included: "",
      excluded: "",
      pattern: "%hsap:N%",
    });

    expect(states.get("hsap")).toBe("exclude");
  });

  it("leaves a code that both lists claim unconstrained and names it", () => {
    const { states, unread } = seedTriStates(roots, {
      included: "hsap, pfal",
      excluded: "hsap",
      pattern: "%",
    });

    expect(states.has("hsap")).toBe(false);
    expect(states.get("pfal")).toBe("include");
    expect(unread).toEqual(["hsap"]);
  });

  it("does not read the pattern when a list carries only an unknown term", () => {
    const { states, unread } = seedTriStates(roots, {
      included: "Nosema",
      excluded: "n/a",
      pattern: "%hsap:Y%",
    });

    expect(states.size).toBe(0);
    expect(unread).toEqual(["Nosema"]);
  });

  it("names the root the reference client stores as unread", () => {
    const { states, unread } = seedTriStates(roots, {
      included: "All Organisms",
      excluded: "n/a",
      pattern: "%",
    });

    expect(states.size).toBe(0);
    expect(unread).toEqual(["All Organisms"]);
  });

  it("names nothing when every stored term is on the tree", () => {
    const { unread } = seedTriStates(roots, {
      included: "pfal",
      excluded: "MAMM",
      pattern: "%",
    });

    expect(unread).toEqual([]);
  });
});

describe("reopening a step whose lists name a term the tree does not carry", () => {
  const specs = makeSpecsFor(CLADE_TERM_MAP, CLADE_INDENT_MAP);
  const stored = {
    phyletic_term_map: CLADE_TERM_MAP,
    phyletic_indent_map: CLADE_INDENT_MAP,
    profile_pattern: "%",
    included_species: "All Organisms",
    excluded_species: "n/a",
  };

  it("shows the term it cannot seed instead of reopening silently empty", () => {
    render(
      <TestForm defaultValues={stored}>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );

    expect(screen.getByTestId("phyletic-unread").textContent).toContain(
      "All Organisms",
    );
  });

  it("paints the unread notice from the warning token", () => {
    render(
      <TestForm defaultValues={stored}>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );

    const notice = screen.getByTestId("phyletic-unread");
    expect(notice).toHaveClass("text-warning");
    expect(notice.className).not.toContain("amber");
  });

  it("paints the include and exclude legend marks from the status tokens", () => {
    render(
      <TestForm defaultValues={stored}>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );

    expect(screen.getByText(String.fromCodePoint(0x2713))).toHaveClass("text-success");
    expect(screen.getByText(String.fromCodePoint(0x2717))).toHaveClass(
      "text-destructive",
    );
  });

  it("shows no notice when every stored term is on the tree", () => {
    render(
      <TestForm defaultValues={{ ...stored, included_species: "pfal" }}>
        {(form) => <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />}
      </TestForm>,
    );

    expect(screen.queryByTestId("phyletic-unread")).toBe(null);
  });
});

describe("reopening a step authored at clade granularity", () => {
  const specs = makeSpecsFor(CLADE_TERM_MAP, CLADE_INDENT_MAP);
  const stored = {
    phyletic_term_map: CLADE_TERM_MAP,
    phyletic_indent_map: CLADE_INDENT_MAP,
    profile_pattern: "%hsap:N%mmus:N%",
    included_species: "n/a",
    excluded_species: "MAMM",
  };

  function renderStored() {
    render(
      <TestForm defaultValues={stored}>
        {(form) => (
          <>
            <PhyleticProfileParam specs={specs} allSpecs={specs} form={form} />
            <FormValueReader form={form} name="included_species" />
            <FormValueReader form={form} name="excluded_species" />
            <FormValueReader form={form} name="profile_pattern" />
          </>
        )}
      </TestForm>,
    );
  }

  function toggleOf(label: string): HTMLElement {
    const row = screen.getByText(label).closest("[data-node]");
    return row!.querySelector("[data-toggle]") as HTMLElement;
  }

  it("shows the stored clade excluded rather than its leaves", () => {
    renderStored();

    expect(toggleOf("Mammalia").textContent).toContain("\u2717");
    expect(toggleOf("H. sapiens").textContent).toContain("\u25CB");
  });

  it("keeps the excluded clade after an unrelated click", () => {
    renderStored();

    fireEvent.click(toggleOf("P. falciparum"));

    expect(screen.getByTestId("form-excluded_species").textContent).toBe("MAMM");
    expect(screen.getByTestId("form-included_species").textContent).toBe("pfal");
  });

  it("still writes the pattern at species granularity", () => {
    renderStored();

    fireEvent.click(toggleOf("P. falciparum"));

    expect(screen.getByTestId("form-profile_pattern").textContent).toBe(
      "%hsap:N%mmus:N%pfal:Y%",
    );
  });
});

describe("leafStates", () => {
  // Clade codes never appear in the census: %MAMM:Y% matches nothing while
  // %hsap:Y% matches. A clade selection has to become its leaves.
  const tree = [
    {
      code: "MAMM",
      label: "Mammals",
      depth: 1,
      children: [
        { code: "hsap", label: "H. sapiens", depth: 2, children: [] },
        { code: "mmus", label: "M. musculus", depth: 2, children: [] },
      ],
    },
    { code: "pfal", label: "P. falciparum", depth: 1, children: [] },
  ];

  it("replaces a clade with its leaves", () => {
    const expanded = leafStates(new Map([["MAMM", "exclude" as const]]), tree);

    expect([...expanded.keys()].sort()).toEqual(["hsap", "mmus"]);
  });

  it("gives every leaf the clade's state", () => {
    const expanded = leafStates(new Map([["MAMM", "exclude" as const]]), tree);

    expect(expanded.get("hsap")).toBe("exclude");
    expect(expanded.get("mmus")).toBe("exclude");
  });

  it("leaves a species alone", () => {
    const expanded = leafStates(new Map([["pfal", "include" as const]]), tree);

    expect([...expanded.entries()]).toEqual([["pfal", "include"]]);
  });

  it("lets an explicit leaf override the clade it sits in", () => {
    const expanded = leafStates(
      new Map([
        ["MAMM", "exclude" as const],
        ["hsap", "include" as const],
      ]),
      tree,
    );

    expect(expanded.get("hsap")).toBe("include");
    expect(expanded.get("mmus")).toBe("exclude");
  });

  it("produces a pattern of leaf tokens only", () => {
    const pattern = encodeProfilePattern(
      leafStates(new Map([["MAMM", "exclude" as const]]), tree),
    );

    expect(pattern).toBe("%hsap:N%mmus:N%");
  });
});

describe("buildSpeciesLists", () => {
  // The reference client reads these two back when reopening a step, and it
  // reads them as vocabulary terms rather than display labels.
  it("writes terms, not labels", () => {
    const lists = buildSpeciesLists(new Map([["pfal", "include" as const]]));

    expect(lists.included).toBe("pfal");
  });

  it("separates several terms the way the reference client does", () => {
    const lists = buildSpeciesLists(
      new Map([
        ["pfal", "include" as const],
        ["hsap", "include" as const],
      ]),
    );

    expect(lists.included).toBe("pfal, hsap");
  });

  it("writes the empty set as the literal the client decodes", () => {
    const lists = buildSpeciesLists(new Map([["pfal", "include" as const]]));

    expect(lists.excluded).toBe("n/a");
  });
});

describe("an included species always reaches the matching branch", () => {
  // The query is a UNION whose first branch fires when the pattern contains no
  // `:Y`, returning the ortholog-less gene set instead of a phyletic match.
  // Every pattern carrying an inclusion must therefore carry a `:Y` token.
  it("writes a :Y token for an inclusion", () => {
    const pattern = encodeProfilePattern(new Map([["pfal", "include" as const]]));

    expect(pattern).toContain(":Y");
  });

  it("writes a :Y even when exclusions outnumber inclusions", () => {
    const pattern = encodeProfilePattern(
      new Map([
        ["hsap", "exclude" as const],
        ["mmus", "exclude" as const],
        ["pfal", "include" as const],
      ]),
    );

    expect(pattern).toContain("pfal:Y");
  });

  it("writes no :Y for an all-exclusion selection, which is its own question", () => {
    // Pure exclusion legitimately means "absent from these, or in no ortholog
    // group", which is the branch the query provides for it.
    const pattern = encodeProfilePattern(new Map([["hsap", "exclude" as const]]));

    expect(pattern).not.toContain(":Y");
  });

  it("never emits the other site's operator grammar", () => {
    const pattern = encodeProfilePattern(
      new Map([
        ["pfal", "include" as const],
        ["hsap", "exclude" as const],
      ]),
    );

    expect(pattern).not.toMatch(/[<>=]/);
  });
});
