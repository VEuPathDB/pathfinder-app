import { DataControlTestResults } from "./parts/DataControlTestResults";
import { DataEvidenceCard } from "./parts/DataEvidenceCard";
import { DataGeneSet } from "./parts/DataGeneSet";
import { DataGraphCleared } from "./parts/DataGraphCleared";
import { DataGraphSnapshot } from "./parts/DataGraphSnapshot";
import { DataScoredComparison } from "./parts/DataScoredComparison";
import { DataSeparationResult } from "./parts/DataSeparationResult";
import { DataStrategyLink } from "./parts/DataStrategyLink";
import { DataStrategyMeta } from "./parts/DataStrategyMeta";
import { DataVariantComparison } from "./parts/DataVariantComparison";
import { noRender } from "./coreDataParts";
import type { DataPartComponentMap } from "./dataPartComponentMap";

/** Parts of the strategy product: graph, strategy, gene sets, controls,
 * comparisons and separations. */
export type StrategyDataPartKind =
  | "data-ledger-update"
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
  | "data-strategy-revision";

export const strategyDataPartComponents: DataPartComponentMap<StrategyDataPartKind> = {
  "data-ledger-update": noRender,
  "data-control-test-results": DataControlTestResults,
  "data-evidence-card": DataEvidenceCard,
  "data-separation-result": DataSeparationResult,
  "data-strategy-link": DataStrategyLink,
  "data-strategy-meta": DataStrategyMeta,
  "data-graph-snapshot": DataGraphSnapshot,
  "data-graph-cleared": DataGraphCleared,
  "data-variant-comparison": DataVariantComparison,
  "data-scored-comparison": DataScoredComparison,
  "data-gene-set": DataGeneSet,
  // SupersededBadge reads the revision off the parts array.
  "data-strategy-revision": noRender,
};
