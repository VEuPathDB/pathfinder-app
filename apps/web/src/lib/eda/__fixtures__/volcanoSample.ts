import type { VolcanoPointInput } from "@/lib/components/charts/types";

/** One point per gene, most from the recorded differentialexpression result. The
 * retained flag is WDK's cut at 1 and 0.05 on the raw p-value. */
export const VOLCANO_POINT_SAMPLE: readonly (VolcanoPointInput & {
  retained: boolean;
})[] = [
  {
    pointId: "PF3D7_0100100",
    effectSize: -0.218035922112735,
    pValue: 0.350285751849808,
    adjustedPValue: 0.46960449943855,
    retained: false,
  },
  {
    pointId: "PF3D7_0100200",
    effectSize: 3.94437533216012,
    pValue: 1.95781599815607e-5,
    adjustedPValue: 0.000137772236907279,
    retained: true,
  },
  {
    pointId: "PF3D7_0100300",
    effectSize: -2.5,
    pValue: 0.001,
    adjustedPValue: 0.004,
    retained: true,
  },
  {
    pointId: "PF3D7_0100400",
    effectSize: 2.78815070709988,
    pValue: 0.0384233901688125,
    adjustedPValue: 0.0779215604822072,
    retained: true,
  },
  {
    pointId: "PF3D7_0100500",
    effectSize: 1.2,
    pValue: 0.2,
    adjustedPValue: 0.4,
    retained: false,
  },
  { pointId: "PF3D7_MIT04200", effectSize: -1.49447459261845, retained: false },
];
