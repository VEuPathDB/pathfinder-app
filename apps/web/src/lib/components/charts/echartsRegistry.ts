import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echartsCore from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import { buildChartTheme, readChartTokens } from "./chartTheme";

echartsCore.use([
  BarChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export function initChart(node: HTMLElement): echartsCore.EChartsType {
  return echartsCore.init(node, buildChartTheme(readChartTokens()), {
    renderer: "canvas",
  });
}
