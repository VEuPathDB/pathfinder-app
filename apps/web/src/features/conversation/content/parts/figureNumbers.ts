import type { UIMessage } from "ai";
import type {
  EdaPcaPart,
  EdaStatisticsPart,
  EdaSubsetPreview,
  EdaViz,
} from "@pathfinder/shared";
import { edaPcaPartSchema } from "@pathfinder/shared/generated/zod/edaPcaPartSchema";
import { edaStatisticsPartSchema } from "@pathfinder/shared/generated/zod/edaStatisticsPartSchema";
import { edaVizPartSchema } from "@pathfinder/shared/generated/zod/edaVizPartSchema";

import { isCurrentWire } from "../currentWire";
import { statisticExhibitKind } from "./statisticExhibit";

const SUBSET_PREVIEW = "data-eda.subset-preview";
const VIZ = "data-eda.viz";
const PCA = "data-eda.pca";
const STATISTICS = "data-eda.statistics";

/** A part the thread numbers as a paper figure. */
type Plot = EdaSubsetPreview | EdaViz | EdaPcaPart | EdaStatisticsPart;

/** The part as a plot, or null when it draws none: a subset preview without a
 * distribution, a statistic that reads as a table, or a stale part. */
function plotOf(type: string, data: unknown): Plot | null {
  switch (type) {
    case VIZ:
      return isCurrentWire(edaVizPartSchema, data) ? data : null;
    case PCA:
      return isCurrentWire(edaPcaPartSchema, data) ? data : null;
    case STATISTICS:
      return isCurrentWire(edaStatisticsPartSchema, data) &&
        statisticExhibitKind(data) === "figure"
        ? data
        : null;
    case SUBSET_PREVIEW: {
      const preview = data as EdaSubsetPreview;
      return preview.distribution !== null ? preview : null;
    }
    default:
      return null;
  }
}

/** The thread's plots, in emission order. */
function plotsOf(messages: readonly UIMessage[]): Plot[] {
  const plots: Plot[] = [];
  for (const message of messages) {
    for (const part of message.parts) {
      if (!("data" in part)) continue;
      const plot = plotOf(part.type, part.data);
      if (plot !== null) plots.push(plot);
    }
  }
  return plots;
}

/** The 1-based number of this plot among the thread's plots. Null when the
 * thread does not carry the payload. Two identical payloads tie on the
 * first. */
export function figureNumberFor(
  messages: readonly UIMessage[],
  data: Plot,
): number | null {
  const wanted = JSON.stringify(data);
  const index = plotsOf(messages).findIndex((plot) => JSON.stringify(plot) === wanted);
  return index === -1 ? null : index + 1;
}
