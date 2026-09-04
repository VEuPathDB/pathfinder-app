"use client";

import { useState } from "react";
import { useIsomorphicLayoutEffect } from "usehooks-ts";
import { VennDiagram, VennSeries, VennArc, VennLabel, ChartTooltip } from "reaviz";
import {
  computeVennData,
  computeExclusiveRegions,
  logScaleVennData,
  type VennInput,
} from "@/features/workbench/utils/vennData";
import {
  CHART_TOKEN_FALLBACKS,
  readChartTokens,
} from "@/lib/components/charts/chartTheme";

type VennLayoutItem = {
  data: { key: string; sets: string[]; size: number };
  text: { x: number; y: number };
  [k: string]: unknown;
};

interface SetVennProps {
  sets: VennInput[];
  height?: number;
  width?: number;
  onRegionClick?: (geneIds: string[], label: string) => void;
}

export function SetVenn({
  sets,
  height = 240,
  width = 380,
  onRegionClick,
}: SetVennProps) {
  const [colors, setColors] = useState(CHART_TOKEN_FALLBACKS.series);
  useIsomorphicLayoutEffect(() => {
    setColors(readChartTokens().series);
  }, []);

  // Real counts for display, log-scaled data for circle sizing
  const realData = computeVennData(sets);
  const data = logScaleVennData(realData);

  // Lookup: joined key → real gene count
  const realCountMap = new Map<string, number>();
  for (const d of realData) {
    realCountMap.set(d.key.join("|"), d.data);
  }

  // Total unique genes across all sets (for percentage calculation)
  const totalGenes = (() => {
    const all = new Set<string>();
    for (const s of sets) {
      for (const g of s.geneIds) all.add(g);
    }
    return all.size;
  })();

  // Format label: show real count and percentage
  const formatLabel = (d: VennLayoutItem) => {
    const realCount = realCountMap.get(d.data.key) ?? Math.round(d.data.size);
    const pct = totalGenes > 0 ? ((realCount / totalGenes) * 100).toFixed(1) : "0.0";
    return `${realCount.toLocaleString()} (${pct}%)`;
  };

  // Format tooltip: show set name(s) with real count
  const formatTooltip = (d: { x: string; y: number }) => {
    const key = d.x.replace(/ \| /g, "|");
    const realCount = realCountMap.get(key) ?? Math.round(d.y);
    return `${d.x}: ${realCount.toLocaleString()}`;
  };

  const exclusiveRegions = onRegionClick ? computeExclusiveRegions(sets) : null;

  const handleArcClick = (event: {
    value: { sets: string[]; size: number };
    nativeEvent: MouseEvent;
  }) => {
    if (!onRegionClick || !exclusiveRegions) return;
    const regionKey = event.value.sets.join(",");
    const geneIds = exclusiveRegions.get(regionKey) ?? [];
    const label =
      event.value.sets.length === 1
        ? `Only ${event.value.sets[0]}`
        : event.value.sets.join(" \u2229 ");
    onRegionClick(geneIds, label);
  };

  if (totalGenes === 0) {
    return (
      <p className="text-[10px] text-muted-foreground">
        These gene sets store no gene IDs, so there is no overlap to draw.
      </p>
    );
  }

  return (
    <div className="flex flex-col items-center gap-1">
      <VennDiagram
        type="euler"
        height={height}
        width={width}
        data={data}
        series={
          <VennSeries
            colorScheme={colors.slice(0, sets.length)}
            label={<VennLabel labelType="value" showAll format={formatLabel} />}
            arc={
              <VennArc
                strokeWidth={1.5}
                {...(onRegionClick != null ? { onClick: handleArcClick } : {})}
                style={{ cursor: onRegionClick != null ? "pointer" : "default" }}
                tooltip={<ChartTooltip content={formatTooltip} />}
              />
            }
          />
        }
      />
      {onRegionClick && (
        <p className="text-[10px] text-muted-foreground">
          Click a region to create a gene set
        </p>
      )}
    </div>
  );
}
