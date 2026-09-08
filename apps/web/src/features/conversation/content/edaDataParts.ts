import { DataEdaAnalysisState } from "./parts/DataEdaAnalysisState";
import { DataEdaSubsetPreview } from "./parts/DataEdaSubsetPreview";
import { DataEdaViz } from "./parts/DataEdaViz";
import type { DataPartComponentMap } from "./dataPartComponentMap";

/** Parts of the EDA surface: the open analysis, the subset, the plot. */
export type EdaDataPartKind =
  "data-eda.analysis-state" | "data-eda.subset-preview" | "data-eda.viz";

export const edaDataPartComponents: DataPartComponentMap<EdaDataPartKind> = {
  "data-eda.analysis-state": DataEdaAnalysisState,
  "data-eda.subset-preview": DataEdaSubsetPreview,
  "data-eda.viz": DataEdaViz,
};
