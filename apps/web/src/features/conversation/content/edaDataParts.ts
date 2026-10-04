import { DataEdaAnalysisState } from "./parts/DataEdaAnalysisState";
import { DataEdaPca } from "./parts/DataEdaPca";
import { DataEdaStatistics } from "./parts/DataEdaStatistics";
import { DataEdaSubsetPreview } from "./parts/DataEdaSubsetPreview";
import { DataEdaViz } from "./parts/DataEdaViz";
import type { DataPartComponentMap } from "./dataPartComponentMap";

/** Parts of the EDA surface: the open analysis, the subset, the plots and the
 * statistics. */
export type EdaDataPartKind =
  | "data-eda.analysis-state"
  | "data-eda.subset-preview"
  | "data-eda.viz"
  | "data-eda.pca"
  | "data-eda.statistics";

export const edaDataPartComponents: DataPartComponentMap<EdaDataPartKind> = {
  "data-eda.analysis-state": DataEdaAnalysisState,
  "data-eda.subset-preview": DataEdaSubsetPreview,
  "data-eda.viz": DataEdaViz,
  "data-eda.pca": DataEdaPca,
  "data-eda.statistics": DataEdaStatistics,
};
