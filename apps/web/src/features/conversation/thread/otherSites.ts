import type { SiteResponse } from "@pathfinder/shared";
import { z } from "zod";

import { siteAppUrl } from "@/lib/sites/siteAppUrl";

const experimentSchema = z.object({
  site: z.string(),
  datasetId: z.string(),
  line: z.string(),
});

export type OtherSiteExperiment = z.infer<typeof experimentSchema>;

const otherSitesEntrySchema = z.object({
  otherSites: z.object({ experiments: z.array(experimentSchema) }),
});

const answerSchema = z.array(z.unknown());

export function otherSiteExperiments(output: unknown): OtherSiteExperiment[] {
  const answer = answerSchema.safeParse(output);
  if (!answer.success) return [];
  for (const entry of answer.data) {
    const parsed = otherSitesEntrySchema.safeParse(entry);
    if (parsed.success) return parsed.data.otherSites.experiments;
  }
  return [];
}

export function placeExperiment(
  experiment: OtherSiteExperiment,
  sites: readonly SiteResponse[],
): { siteName: string; recordUrl: string | null } {
  const site = sites.find((candidate) => candidate.id === experiment.site);
  if (site === undefined) return { siteName: experiment.site, recordUrl: null };
  return {
    siteName: site.displayName,
    recordUrl: siteAppUrl(
      site,
      `/app/record/dataset/${encodeURIComponent(experiment.datasetId)}`,
    ),
  };
}
