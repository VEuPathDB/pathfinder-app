"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactElement } from "react";

import { sitesOptions } from "@/lib/api/sites";

import { placeExperiment, type OtherSiteExperiment } from "./otherSites";

export function RelatedExperiments({
  experiments,
}: {
  experiments: readonly OtherSiteExperiment[];
}): ReactElement {
  const { data: sites = [] } = useQuery(sitesOptions());
  return (
    <ul data-testid="trace-row-other-sites" className="space-y-0.5 py-1 pl-5 text-xs">
      {experiments.map((experiment) => {
        const { siteName, recordUrl } = placeExperiment(experiment, sites);
        return (
          <li key={experiment.datasetId} className="flex items-baseline gap-2">
            {recordUrl === null ? (
              <span className="text-foreground/80">{experiment.line}</span>
            ) : (
              <a
                href={recordUrl}
                target="_blank"
                rel="noreferrer"
                className="text-foreground/80 underline underline-offset-2 hover:text-foreground"
              >
                {experiment.line}
              </a>
            )}
            <span className="shrink-0 text-muted-foreground">{siteName}</span>
          </li>
        );
      })}
    </ul>
  );
}
