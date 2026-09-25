import { describe, expect, it } from "vitest";

import { VOLCANO_POINT_SAMPLE } from "./__fixtures__/volcanoSample";
import { selectVolcanoGenes } from "./volcanoSelection";
import type { VolcanoPointInput } from "@/lib/components/charts/types";

/** A recorded row carries the backend's retained flag beside the point. */
type RecordedPoint = VolcanoPointInput & { retained: boolean };

const thresholds = {
  effectSizeThreshold: 1,
  significanceThreshold: 0.05,
  direction: "upAndDown" as const,
};

describe("selectVolcanoGenes", () => {
  it("splits the recorded sample into two up genes and one down gene", () => {
    const result = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, thresholds);
    expect(result.up).toEqual(["PF3D7_0100200", "PF3D7_0100400"]);
    expect(result.down).toEqual(["PF3D7_0100300"]);
    expect(result.selected).toEqual([
      "PF3D7_0100200",
      "PF3D7_0100400",
      "PF3D7_0100300",
    ]);
  });

  it("agrees with WDK's cut on the raw p-value, which keeps a gene the adjusted one drops", () => {
    const result = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, thresholds);
    const serverRetained = VOLCANO_POINT_SAMPLE.filter((p) => p.retained).map(
      (p) => p.pointId,
    );
    expect([...result.selected].sort()).toEqual([...serverRetained].sort());
  });

  it("drops the point that carries no p-value and counts it", () => {
    const result = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, thresholds);
    expect(result.droppedRowCount).toBe(1);
    expect(result.selected).not.toContain("PF3D7_MIT04200");
  });

  it("drops a point whose p-value is explicitly null", () => {
    const points: RecordedPoint[] = [
      { pointId: "NULLP", effectSize: 4, pValue: null, retained: false },
    ];
    const result = selectVolcanoGenes(points, thresholds);
    expect(result.droppedRowCount).toBe(1);
    expect(result.selected).toEqual([]);
  });

  it("honours direction upOnly", () => {
    const result = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, {
      ...thresholds,
      direction: "upOnly",
    });
    expect(result.selected).toEqual(["PF3D7_0100200", "PF3D7_0100400"]);
  });

  it("honours direction downOnly", () => {
    const result = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, {
      ...thresholds,
      direction: "downOnly",
    });
    expect(result.selected).toEqual(["PF3D7_0100300"]);
  });

  it("admits a gene at a looser p cut", () => {
    const result = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, {
      effectSizeThreshold: 1,
      significanceThreshold: 0.3,
      direction: "upAndDown",
    });
    expect(result.up).toEqual(["PF3D7_0100200", "PF3D7_0100400", "PF3D7_0100500"]);
    expect(result.down).toEqual(["PF3D7_0100300"]);
  });

  it("keeps a gene whose p-value equals the cut, as WDK does", () => {
    const points: RecordedPoint[] = [
      { pointId: "AT", effectSize: 2, pValue: 0.05, retained: true },
      { pointId: "ABOVE", effectSize: 2, pValue: 0.051, retained: false },
    ];
    const result = selectVolcanoGenes(points, thresholds);
    expect(result.selected).toEqual(["AT"]);
  });

  it("treats the effect-size threshold as inclusive on the absolute value", () => {
    const points: RecordedPoint[] = [
      { pointId: "EXACT", effectSize: 1, pValue: 0.01, retained: true },
      { pointId: "UNDER", effectSize: 0.999, pValue: 0.01, retained: false },
    ];
    const result = selectVolcanoGenes(points, thresholds);
    expect(result.selected).toEqual(["EXACT"]);
  });

  it("never grows the selection when the effect-size threshold rises", () => {
    let previous: string[] | null = null;
    for (const effectSizeThreshold of [0.5, 1, 1.5, 2, 3, 4.5]) {
      const result = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, {
        ...thresholds,
        effectSizeThreshold,
      });
      if (previous !== null) {
        const kept = previous;
        expect(result.selected.every((id) => kept.includes(id))).toBe(true);
      }
      previous = result.selected;
    }
    expect(previous).toEqual([]);
  });

  it("partitions the upAndDown selection into the up and down halves", () => {
    const both = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, thresholds);
    const up = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, {
      ...thresholds,
      direction: "upOnly",
    });
    const down = selectVolcanoGenes(VOLCANO_POINT_SAMPLE, {
      ...thresholds,
      direction: "downOnly",
    });
    expect([...up.selected, ...down.selected].sort()).toEqual(
      [...both.selected].sort(),
    );
    expect(up.selected.filter((id) => down.selected.includes(id))).toEqual([]);
    expect(both.up).toEqual(up.selected);
    expect(both.down).toEqual(down.selected);
  });
});
