import { describe, expect, it } from "vitest";
import type { EdaEntityResponse } from "@pathfinder/shared/generated/types/EdaEntityResponse";

import {
  buildEntityTree,
  collectEntityIds,
  draftToFilter,
  edaDateBound,
  editableFilterType,
  findFilter,
  isDraftApplicable,
  isHiddenFromTree,
  removeFilter,
  upsertFilter,
} from "./filterDrafts";

const FEBRILE = {
  entityId: "ENT_8151325d",
  variableId: "VAR_081ab087",
  type: "stringSet" as const,
  stringSet: ["febrile"],
};

const SAMPLE: EdaEntityResponse = {
  entityId: "ENT_8151325d",
  displayName: "Sample",
  displayNamePlural: "Samples",
  parentEntityId: null,
  variableCount: 2,
  hasGeneId: false,
};

const COUNTS: EdaEntityResponse = {
  entityId: "ENT_fd574cd6",
  displayName: "pfal3D7 htseq counts",
  displayNamePlural: "pfal3D7 htseq counts",
  parentEntityId: "ENT_8151325d",
  variableCount: 2,
  hasGeneId: true,
};

describe("edaDateBound", () => {
  it("appends the time part the service requires", () => {
    expect(edaDateBound("2017-05-05")).toBe("2017-05-05T00:00:00");
  });

  it("leaves a bound that already carries a time part alone", () => {
    expect(edaDateBound("2017-05-05T00:00:00")).toBe("2017-05-05T00:00:00");
  });

  it("leaves a bound with a zulu suffix alone", () => {
    expect(edaDateBound("2017-05-05T00:00:00Z")).toBe("2017-05-05T00:00:00Z");
  });
});

describe("upsertFilter", () => {
  it("appends a filter for a variable that has none", () => {
    expect(upsertFilter([], FEBRILE)).toEqual([FEBRILE]);
  });

  it("replaces the filter on the same entity and variable rather than adding a second", () => {
    const next = upsertFilter([FEBRILE], { ...FEBRILE, stringSet: ["normal"] });
    expect(next).toHaveLength(1);
    expect(next[0]).toEqual({ ...FEBRILE, stringSet: ["normal"] });
  });

  it("keeps a filter on a different variable of the same entity", () => {
    const other = {
      entityId: "ENT_8151325d",
      variableId: "VAR_7033e90f",
      type: "numberRange" as const,
      min: 37,
      max: 42,
    };
    expect(upsertFilter([FEBRILE], other)).toEqual([FEBRILE, other]);
  });
});

describe("removeFilter", () => {
  it("removes by entity and variable", () => {
    expect(removeFilter([FEBRILE], "ENT_8151325d", "VAR_081ab087")).toEqual([]);
  });

  it("leaves the array alone when nothing matches", () => {
    expect(removeFilter([FEBRILE], "ENT_8151325d", "VAR_other")).toEqual([FEBRILE]);
  });
});

describe("findFilter", () => {
  it("returns the filter on the named entity and variable", () => {
    expect(findFilter([FEBRILE], "ENT_8151325d", "VAR_081ab087")).toEqual(FEBRILE);
  });

  it("returns null when the same variable id sits on another entity", () => {
    expect(findFilter([FEBRILE], "ENT_fd574cd6", "VAR_081ab087")).toBe(null);
  });
});

describe("isDraftApplicable", () => {
  it("refuses an empty stringSet, which the service rejects with a 400", () => {
    expect(isDraftApplicable({ kind: "stringSet", values: [] })).toBe(false);
  });

  it("accepts a stringSet with one value", () => {
    expect(isDraftApplicable({ kind: "stringSet", values: ["febrile"] })).toBe(true);
  });

  it("refuses a numberRange with a non-numeric bound", () => {
    expect(isDraftApplicable({ kind: "numberRange", min: "", max: "42" })).toBe(false);
  });

  it("accepts a numberRange whose min exceeds its max, which the service answers with count 0", () => {
    expect(isDraftApplicable({ kind: "numberRange", min: "100", max: "0" })).toBe(true);
  });

  it("refuses a dateRange with an empty bound", () => {
    expect(isDraftApplicable({ kind: "dateRange", min: "2017-05-05", max: "" })).toBe(
      false,
    );
  });
});

describe("editableFilterType", () => {
  it("keeps the three types the tab can edit", () => {
    expect(editableFilterType("stringSet")).toBe("stringSet");
    expect(editableFilterType("numberRange")).toBe("numberRange");
    expect(editableFilterType("dateRange")).toBe("dateRange");
  });

  it("refuses the set and nested types, which only chat can author", () => {
    expect(editableFilterType("numberSet")).toBe(null);
    expect(editableFilterType("dateSet")).toBe(null);
    expect(editableFilterType("longitudeRange")).toBe(null);
    expect(editableFilterType("multiFilter")).toBe(null);
  });

  it("refuses a variable the service declares unfilterable", () => {
    expect(editableFilterType(null)).toBe(null);
    expect(editableFilterType(undefined)).toBe(null);
  });
});

describe("draftToFilter", () => {
  it("builds a stringSet filter from the checked values", () => {
    expect(
      draftToFilter("ENT_8151325d", "VAR_081ab087", {
        kind: "stringSet",
        values: ["febrile"],
      }),
    ).toEqual(FEBRILE);
  });

  it("parses number bounds into numbers, not strings", () => {
    expect(
      draftToFilter("ENT_8151325d", "VAR_7033e90f", {
        kind: "numberRange",
        min: "37",
        max: "42",
      }),
    ).toEqual({
      entityId: "ENT_8151325d",
      variableId: "VAR_7033e90f",
      type: "numberRange",
      min: 37,
      max: 42,
    });
  });

  it("gives both date bounds the time part the service requires", () => {
    expect(
      draftToFilter("OBI_0000659", "EUPATH_0043256", {
        kind: "dateRange",
        min: "2017-05-05",
        max: "2017-05-11",
      }),
    ).toEqual({
      entityId: "OBI_0000659",
      variableId: "EUPATH_0043256",
      type: "dateRange",
      min: "2017-05-05T00:00:00",
      max: "2017-05-11T00:00:00",
    });
  });
});

describe("buildEntityTree", () => {
  it("returns nothing for a study that declares no entity", () => {
    expect(buildEntityTree([])).toBe(null);
  });

  it("hangs a child under the parent the wire names", () => {
    expect(buildEntityTree([SAMPLE, COUNTS])).toEqual({
      entityId: "ENT_8151325d",
      displayName: "Sample",
      children: [
        { entityId: "ENT_fd574cd6", displayName: "pfal3D7 htseq counts", children: [] },
      ],
    });
  });

  it("takes the entity with no parent as the root, whatever the wire order", () => {
    expect(buildEntityTree([COUNTS, SAMPLE])?.entityId).toBe("ENT_8151325d");
  });
});

describe("collectEntityIds", () => {
  it("returns nothing for an absent tree", () => {
    expect(collectEntityIds(null)).toEqual([]);
  });

  it("returns a single node's id", () => {
    expect(
      collectEntityIds({ entityId: "ENT_only", displayName: "Only", children: [] }),
    ).toEqual(["ENT_only"]);
  });

  it("walks the tree root first", () => {
    expect(collectEntityIds(buildEntityTree([SAMPLE, COUNTS]))).toEqual([
      "ENT_8151325d",
      "ENT_fd574cd6",
    ]);
  });
});

describe("isHiddenFromTree", () => {
  it("hides a variable the study hides everywhere", () => {
    expect(isHiddenFromTree({ hideFrom: ["everywhere"] })).toBe(true);
  });

  it("hides a variable the study hides from the variable tree", () => {
    expect(isHiddenFromTree({ hideFrom: ["variableTree"] })).toBe(true);
  });

  it("keeps a variable hidden only from the map and the download", () => {
    expect(isHiddenFromTree({ hideFrom: ["map", "download"] })).toBe(false);
  });

  it("keeps a variable the study hides from nothing", () => {
    expect(isHiddenFromTree({ hideFrom: [] })).toBe(false);
  });
});
