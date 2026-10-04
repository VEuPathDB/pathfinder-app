"use client";

import type { EdaPcaPart } from "@pathfinder/shared";
import { edaPcaPartSchema } from "@pathfinder/shared/generated/zod/edaPcaPartSchema";

import { Figure } from "@/features/conversation/thread/Figure";
import { ScatterChart } from "@/lib/components/charts/ScatterChart";
import type { EdaAxisLabel } from "@/lib/components/charts/types";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { StalePartNotice } from "../StalePartNotice";
import { isCurrentWire } from "../currentWire";
import { studyNameFor } from "./analysisStateParts";
import { figureNumberFor } from "./figureNumbers";
import { plotCaption } from "./plotCaptions";

const PCA_HEIGHT = 320;

export function DataEdaPca({ data }: { data: unknown }) {
  const part = isCurrentWire(edaPcaPartSchema, data) ? data : null;
  const [xAxis, yAxis] = part?.axes ?? [];
  if (part === null || xAxis === undefined || yAxis === undefined) {
    return <StalePartNotice subject="A plot" />;
  }
  return <PcaFigure data={part} xAxis={xAxis} yAxis={yAxis} />;
}

interface PcaFigureProps {
  data: EdaPcaPart;
  xAxis: EdaAxisLabel;
  yAxis: EdaAxisLabel;
}

function PcaFigure({ data, xAxis, yAxis }: PcaFigureProps) {
  const chat = useChatHelpers();
  const study = studyNameFor(chat.messages, data.analysisId);
  const counts = `${data.sampleCount.toLocaleString()} ${data.sampleCount === 1 ? "sample" : "samples"}, ${data.groupCount.toLocaleString()} ${data.groupCount === 1 ? "group" : "groups"}`;

  return (
    <Figure
      testId="data-eda-pca"
      title="Principal component analysis"
      caption={plotCaption(data.caption ?? "", study, counts)}
      exhibit={{ kind: "figure", number: figureNumberFor(chat.messages, data) }}
    >
      <ScatterChart
        series={data.series.map((group) => ({
          name: group.label,
          x: group.x,
          y: group.y,
          pointIds: group.sampleIds,
        }))}
        xAxis={xAxis}
        yAxis={yAxis}
        height={PCA_HEIGHT}
        testId="eda-pca-scatter"
      />
    </Figure>
  );
}
