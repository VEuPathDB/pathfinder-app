import { DataFactsNotices } from "./parts/DataFactsNotices";
import { DataGeneSet } from "./parts/DataGeneSet";
import { DataGeneSetList } from "./parts/DataGeneSetList";
import { DataGraphCleared } from "./parts/DataGraphCleared";
import { DataScoredComparison } from "./parts/DataScoredComparison";
import { DataSeparationResult } from "./parts/DataSeparationResult";
import { DataVariantComparison } from "./parts/DataVariantComparison";
import { noRender } from "./coreDataParts";
import type { DataPartComponentMap } from "./dataPartComponentMap";

/** Parts of the strategy product: graph, strategy, gene sets, controls,
 * comparisons, separations, and the facts a turn shows beside its reply. */
export type StrategyDataPartKind =
  | "data-ledger-update"
  | "data-facts"
  | "data-control-test-results"
  | "data-evidence-card"
  | "data-separation-result"
  | "data-strategy-link"
  | "data-strategy-meta"
  | "data-graph-snapshot"
  | "data-graph-cleared"
  | "data-variant-comparison"
  | "data-scored-comparison"
  | "data-gene-set"
  | "data-gene-set-list"
  | "data-strategy-revision"
  | "data-delete-cascade";

export const strategyDataPartComponents: DataPartComponentMap<StrategyDataPartKind> = {
  "data-ledger-update": noRender,
  "data-facts": DataFactsNotices,
  "data-control-test-results": noRender,
  "data-evidence-card": noRender,
  "data-separation-result": DataSeparationResult,
  "data-strategy-link": noRender,
  "data-strategy-meta": noRender,
  "data-graph-snapshot": noRender,
  "data-graph-cleared": DataGraphCleared,
  "data-variant-comparison": DataVariantComparison,
  "data-scored-comparison": DataScoredComparison,
  "data-gene-set": DataGeneSet,
  "data-gene-set-list": DataGeneSetList,
  // SupersededBadge reads the revision off the parts array.
  "data-strategy-revision": noRender,
  // The approval card reads the cascade off the parts array.
  "data-delete-cascade": noRender,
};
