import { describe, expect, it } from "vitest";

import { selectVolcanoGenes, VOLCANO_POINT_SAMPLE } from "./volcanoSelection";
import type { VolcanoPointInput } from "@/lib/components/charts/types";

/** A recorded row carries the backend's retained flag beside the point. */
type RecordedPoint = VolcanoPointInput & { retained: boolean };

const thresholds = {
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  direction: "upAndDown" as const,
};

describe("selectVolcanoGenes", () => {
  it("splits the recorded sample into one up and one down gene", () => {
    const result = selectVolcanoGenes(
      VOLCANO_POINT_SAMPLE,
      thresholds,
      "adjustedPValue",
    );
    expect(result.up).toEqual(["PF3D7_0100200"]);
    expect(result.down).toEqual(["PF3D7_0100300"]);
    expect(result.selected).toEqual(["PF3D7_0100200", "PF3D7_0100300"]);
  });

  it("agrees with the retained flag the backend computed at the same thresholds", () => {
    const result = selectVolcanoGenes(
      VOLCANO_POINT_SAMPLE,
      thresholds,
      "adjustedPValue",
    );
    const serverRetained = VOLCANO_POINT_SAMPLE.filter((p) => p.retained).map(
      (p) => p.pointId,
    );
    expect([...result.selected].sort()).toEqual([...serverRetained].sort());
  });

  it("drops the point that carries no p-value and counts it", () => {
    const result = selectVolcanoGenes(
      VOLCANO_POINT_SAMPLE,
      thresholds,
      "adjustedPValue",
    );
    expect(result.droppedRowCount).toBe(1);
    expect(result.selected).not.toContain("PF3D7_MIT04200");
  });

  it("drops a point whose p-value is explicitly null", () => {
    const points: RecordedPoint[] = [
      { pointId: "NULLP", effectSize: 4, adjustedPValue: null, retained: false },
    ];
    const result = selectVolcanoGenes(points, thresholds, "adjustedPValue");
    expect(result.droppedRowCount).toBe(1);
    expect(result.selected).toEqual([]);
  });

  it("honours direction upOnly", () => {
    const result = selectVolcanoGenes(
      VOLCANO_POINT_SAMPLE,
      { ...thresholds, direction: "upOnly" },
      "adjustedPValue",
    );
    expect(result.selected).toEqual(["PF3D7_0100200"]);
  });

  it("honours direction downOnly", () => {
    const result = selectVolcanoGenes(
      VOLCANO_POINT_SAMPLE,
      { ...thresholds, direction: "downOnly" },
      "adjustedPValue",
    );
    expect(result.selected).toEqual(["PF3D7_0100300"]);
  });

  it("selects on the raw p-value when asked, which admits a third gene", () => {
    const result = selectVolcanoGenes(
      VOLCANO_POINT_SAMPLE,
      {
        effectSizeThreshold: 1,
        significanceThreshold: 0.3,
        direction: "upAndDown",
      },
      "pValue",
    );
    expect(result.up).toEqual(["PF3D7_0100200", "PF3D7_0100500"]);
    expect(result.down).toEqual(["PF3D7_0100300"]);
  });

  it("treats the significance threshold as strict", () => {
    const points: RecordedPoint[] = [
      { pointId: "AT", effectSize: 2, adjustedPValue: 0.05, retained: false },
      { pointId: "BELOW", effectSize: 2, adjustedPValue: 0.049, retained: true },
    ];
    const result = selectVolcanoGenes(points, thresholds, "adjustedPValue");
    expect(result.selected).toEqual(["BELOW"]);
  });

  it("treats the effect-size threshold as inclusive on the absolute value", () => {
    const points: RecordedPoint[] = [
      { pointId: "EXACT", effectSize: 1, adjustedPValue: 0.01, retained: true },
      { pointId: "UNDER", effectSize: 0.999, adjustedPValue: 0.01, retained: false },
    ];
    const result = selectVolcanoGenes(points, thresholds, "adjustedPValue");
    expect(result.selected).toEqual(["EXACT"]);
  });

  it("never grows the selection when the effect-size threshold rises", () => {
    let previous: string[] | null = null;
    for (const effectSizeThreshold of [0.5, 1, 1.5, 2, 3, 4.5]) {
      const result = selectVolcanoGenes(
        VOLCANO_POINT_SAMPLE,
        { ...thresholds, effectSizeThreshold },
        "adjustedPValue",
      );
      if (previous !== null) {
        const kept = previous;
        expect(result.selected.every((id) => kept.includes(id))).toBe(true);
      }
      previous = result.selected;
    }
    expect(previous).toEqual([]);
  });

  it("partitions the upAndDown selection into the up and down halves", () => {
    const both = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, thresholds, "adjustedPValue");
    const up = selectVolcanoGenes(
      VOLCANO_POINT_SAMPLE,
      { ...thresholds, direction: "upOnly" },
      "adjustedPValue",
    );
    const down = selectVolcanoGenes(
      VOLCANO_POINT_SAMPLE,
      { ...thresholds, direction: "downOnly" },
      "adjustedPValue",
    );
    expect([...up.selected, ...down.selected].sort()).toEqual(
      [...both.selected].sort(),
    );
    expect(up.selected.filter((id) => down.selected.includes(id))).toEqual([]);
    expect(both.up).toEqual(up.selected);
    expect(both.down).toEqual(down.selected);
  });
});
