import type { EdaStatisticsPart } from "@pathfinder/shared";

import type { ExhibitKind } from "../../thread/exhibits";

/** A box plot and a trend draw a chart and number among the figures; a
 * two-by-two and a contingency number among the tables. */
export function statisticExhibitKind(data: EdaStatisticsPart): ExhibitKind {
  return data.kind === "boxplot" || data.kind === "trend" ? "figure" : "table";
}
