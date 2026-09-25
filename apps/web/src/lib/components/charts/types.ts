/** One gene of a differential expression result, as the part carries it. */
export interface VolcanoPointInput {
  pointId: string;
  effectSize: number;
  pValue?: number | null;
  adjustedPValue?: number | null;
}

export type VolcanoDirection = "upOnly" | "downOnly" | "upAndDown";

export interface VolcanoThresholds {
  effectSizeThreshold: number;
  significanceThreshold: number;
  direction: VolcanoDirection;
}

/** Parallel label and value arrays, the shape both EDA distributions and EDA
 * barplots arrive in. */
export interface EdaCategorySeries {
  name: string;
  labels: string[];
  values: number[];
}

export interface EdaScatterSeries {
  name: string;
  x: number[];
  y: number[];
  pointIds?: string[];
}

export interface EdaAxisLabel {
  variableId: string;
  displayName: string;
}
